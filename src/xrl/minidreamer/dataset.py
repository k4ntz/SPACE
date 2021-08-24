import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset

class ModelDataset(Dataset):
    def __init__(self, history, seq_len, history_size):
        self.h = history #history is passed as list and updated outside
        self.seq_len = seq_len
        self.history_size = history_size

    def __len__(self):
        return self.history_size

    def __getitem__(self, idx):
        idx = idx % len(self.h) #do not exceed history length
        episode = self.h[idx]

        idx_sample = np.random.randint(0, (len(episode)-1)//4) #sample random part of episode
        idx_sample = min(idx_sample, (len(episode)-1)//4 - self.seq_len) #clip to not exceed limit

        # one entry is last state, action, state and reward as seperate entries
        last_states = episode[idx_sample * 4 : idx_sample * 4 + self.seq_len * 4 : 4]
        actions= episode[idx_sample * 4 + 1 : idx_sample * 4 + self.seq_len * 4 + 1 : 4]
        states = episode[idx_sample * 4 + 2 : idx_sample * 4 + self.seq_len * 4 + 2 : 4]
        rewards= episode[idx_sample * 4 + 3 : idx_sample * 4 + self.seq_len * 4 + 3 : 4]

        last_states = torch.cat(last_states)
        actions = torch.cat(actions)
        states = torch.cat(states)
        rewards = torch.Tensor(rewards)

        return last_states, actions, states, rewards