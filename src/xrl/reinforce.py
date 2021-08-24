from operator import mod
import gym
import numpy as np
import os

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.modules import module
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter
from torch.distributions import Categorical
from atariari.benchmark.wrapper import AtariARIWrapper
from captum.attr import IntegratedGradients

from rtpt import RTPT

import xrl.utils as xutils
import xrl.video_logger as vlogger
import xrl.pruner as pruner

PATH_TO_OUTPUTS = os.getcwd() + "/xrl/checkpoints/"
if not os.path.exists(PATH_TO_OUTPUTS):
    os.makedirs(PATH_TO_OUTPUTS)

model_name = lambda training_name : PATH_TO_OUTPUTS + training_name + "_model.pth"


# with preprocessed meaningful features
class Policy(nn.Module):
    def __init__(self, input, hidden, actions): 
        super(Policy, self).__init__()
        self.h = nn.Linear(input, hidden)
        self.out = nn.Linear(hidden, actions)

        self.saved_log_probs = []
        self.rewards = []

    def forward(self, x):
        x = F.relu(self.h(x))
        return F.softmax(self.out(x), dim=1)


# with raw image as input
class CNNPolicy(nn.Module):
    def __init__(self, actions): 
        super(CNNPolicy, self).__init__()
        # 2 conv layers for image to raw features
        self.conv1 = nn.Conv2d(in_channels=4,  out_channels=32, kernel_size=3)
        self.bn1 = nn.BatchNorm2d(32)
        self.conv2 = nn.Conv2d(in_channels=32,  out_channels=16, kernel_size=2)
        self.bn2 = nn.BatchNorm2d(16)

        # fcl 
        # first hidden layer raw features to meaningful features
        self.h = nn.Linear(59536, 64)
        self.h2 = nn.Linear(64, 32)
        self.out = nn.Linear(32, actions)       # b: only two hidden layers with x->64->64->actions

        self.saved_log_probs = []
        self.rewards = []

    def forward(self, x):
        # conv
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        # flatten
        x = x.view(x.size(0), -1) 
        # fcl
        x = F.relu(self.h(x))
        x = F.relu(self.h2(x))
        return F.softmax(self.out(x), dim=1)


# helper function to return correct network
def get_network(cfg, input, hidden, actions):
    if not cfg.raw_image:
        print("Policy net has", input, "input nodes,", hidden, "hidden nodes and", actions, "output nodes")
        return Policy(input, hidden, actions)
    else: 
        return CNNPolicy(actions)


def select_action(features, policy):
    input = torch.tensor(features).unsqueeze(0).float()
    probs = policy(input)
    #print(list(np.around(probs.detach().numpy(), 3)))
    m = Categorical(probs)
    action = m.sample()
    log_prob = m.log_prob(action)
    return action.item(), log_prob


def finish_episode(policy, optimizer, eps, cfg):
    R = 0
    policy_loss = []
    returns = []
    for r in policy.rewards[::-1]:
        R = r + cfg.train.gamma * R
        returns.insert(0, R)
    returns = torch.tensor(returns)
    returns = (returns - returns.mean()) / (returns.std() + eps)
    for log_prob, R in zip(policy.saved_log_probs, returns):
        policy_loss.append(-log_prob * R)
    optimizer.zero_grad()
    policy_loss = torch.cat(policy_loss).sum()
    policy_loss.backward()
    optimizer.step()
    del policy.rewards[:]
    del policy.saved_log_probs[:]
    return policy, optimizer

# save model helper function
def save_policy(training_name, policy, episode, optimizer):
    if not os.path.exists(PATH_TO_OUTPUTS):
        os.makedirs(PATH_TO_OUTPUTS)
    model_path = model_name(training_name)
    print("Saving {}".format(model_path))
    torch.save({
            'policy': policy.state_dict(),
            'episode': episode,
            'optimizer': optimizer.state_dict()
            }, model_path)


# load model
def load_model(model_path, policy, optimizer=None):
    print("{} does exist, loading ... ".format(model_path))
    checkpoint = torch.load(model_path)
    policy.load_state_dict(checkpoint['policy'])
    if optimizer is not None:
        optimizer.load_state_dict(checkpoint['optimizer'])
    i_episode = checkpoint['episode']
    return policy, optimizer, i_episode


def train(cfg):
    print('Experiment name:', cfg.exp_name)
    writer = SummaryWriter(os.getcwd() + cfg.logdir + cfg.exp_name)
    # init env to get params for policy net
    env = AtariARIWrapper(gym.make(cfg.env_name))
    n_actions = env.action_space.n
    _ = env.reset()
    _, features, _, _ = xutils.do_step(env)
    # init policy net
    policy = get_network(cfg, len(features), cfg.train.hidden_layer_size, n_actions)
    optimizer = optim.Adam(policy.parameters(), lr=cfg.train.learning_rate) 
    eps = np.finfo(np.float32).eps.item()
    i_episode = 1
    # load if exists
    model_path = model_name(cfg.exp_name)
    if os.path.isfile(model_path):
        policy, optimizer, i_episode = load_model(model_path, policy, optimizer)
    print('Episodes:', cfg.train.num_episodes)
    print('Max Steps per Episode:', cfg.train.max_steps)
    print('Gamma:', cfg.train.gamma)
    print('Learning rate:', cfg.train.learning_rate)
    running_reward = None
    reward_buffer = 0
    # training loop
    rtpt = RTPT(name_initials='DV', experiment_name=cfg.exp_name,
                    max_iterations=cfg.train.num_episodes)
    rtpt.start()
    while i_episode <= cfg.train.num_episodes:
        # init env
        _, ep_reward = env.reset(), 0
        _, _, done, _ = env.step(1)
        raw_features, features, _, _ = xutils.do_step(env, raw_image=cfg.raw_image)
        # env loop
        t = 0
        while t < cfg.train.max_steps:  # Don't infinite loop while learning
            action, log_prob = select_action(features, policy)
            policy.saved_log_probs.append(log_prob)
            raw_features, features, reward, done = xutils.do_step(env, action, raw_features, raw_image=cfg.raw_image)
            if cfg.liveplot:
                xutils.plot_screen(env, i_episode, t)
            policy.rewards.append(reward)
            ep_reward += reward
            t += 1
            if done:
                break
        # only optimize when t < max ep steps
        if t >= cfg.train.max_steps:
            ep_reward = -25 #TODO: change to automatically game specific
        # finish episode and optimize nn
        # replace first running reward with last reward for loaded models
        if running_reward is None:
            running_reward = ep_reward
        else:
            running_reward = 0.05 * ep_reward + (1 - 0.05) * running_reward
        reward_buffer += ep_reward
        policy, optimizer = finish_episode(policy, optimizer, eps, cfg)
        print('Episode {}\tLast reward: {:.2f}\tRunning reward: {:.2f}\tSteps: {}       '.format(
            i_episode, ep_reward, running_reward, t), end="\r")
        if i_episode % cfg.train.log_steps == 0:
            avg_r = reward_buffer / cfg.train.log_steps
            writer.add_scalar('Train/Avg reward', avg_r, i_episode)
            reward_buffer = 0
        if i_episode % cfg.train.save_every == 0:
            save_policy(cfg.exp_name, policy, i_episode + 1, optimizer)
        i_episode += 1
        rtpt.step()


# eval function 
def eval(cfg):
    print('Experiment name:', cfg.exp_name)
    print('Evaluating Mode')
    # disable gradients as we will not use them
    torch.set_grad_enabled(False)
    # init video logger
    logger = vlogger.VideoLogger(size=(480,480))
    # init env 
    env = AtariARIWrapper(gym.make(cfg.env_name))
    n_actions = env.action_space.n
    _, ep_reward = env.reset(), 0
    _, _, done, _ = env.step(1)
    raw_features, features, _, _ = xutils.do_step(env, raw_image=cfg.raw_image)
    policy = get_network(cfg, len(features), cfg.train.hidden_layer_size, n_actions)
    i_episode = 1
    # load if exists
    model_path = model_name(cfg.exp_name)
    if os.path.isfile(model_path):
        policy, _, i_episode = load_model(model_path, policy)
    policy.eval()
    # init intgrad
    ig = IntegratedGradients(policy)
    ig_sum = []
    feature_titles = xutils.get_feature_titles()
    # env loop
    t = 0
    while t  < cfg.train.max_steps:  # Don't infinite loop while playing
        action, _ = select_action(features, policy)
        if cfg.liveplot or cfg.make_video:
            img = xutils.plot_integrated_gradient_img(ig, cfg.exp_name, features, feature_titles, action, env, cfg.liveplot)
            logger.fill_video_buffer(img)
            print('Episode {}\tReward: {:.2f}\t Step: {:.2f}'.format(
                i_episode, ep_reward, t), end="\r")
        else:
            ig_sum.append(xutils.get_integrated_gradients(ig, features, action))
            print('Episode {}\tReward: {:.2f}\t Step: {:.2f}'.format(
                i_episode, ep_reward, t), end="\r")
        raw_features, features, reward, done = xutils.do_step(env, action, raw_features, raw_image=cfg.raw_image)
        ep_reward += reward
        t += 1
        if done:
            break
    if cfg.liveplot or cfg.make_video:
        logger.save_video(cfg.exp_name)
        print('Episode {}\tReward: {:.2f}'.format(
        i_episode, ep_reward))
    else:
        ig_sum = np.asarray(ig_sum)
        print('Episode {}\tReward: {:.2f}\tSteps: {}\tIG-Mean: {}'.format(
        i_episode, ep_reward, t, np.mean(ig_sum, axis=0)))
        # prune 
        policy = pruner.prune_nn(policy, "ig-pr", np.mean(ig_sum, axis=0))
        #xutils.plot_igs(ig_sum, feature_titles)
