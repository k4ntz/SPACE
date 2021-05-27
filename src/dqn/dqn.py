# nn for dq learning

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import torchvision.transforms as T

# if gpu is to be used
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class DQN(nn.Module):

    def __init__(self, outputs):
        super(DQN, self).__init__()
        self.conv1 = nn.Conv2d(1, 16, kernel_size=3, stride=2)
        self.bn1 = nn.BatchNorm2d(16)

        self.head = nn.Linear(10224, outputs)

    # Called with either one element to determine next action, or a batch
    # during optimization. Returns tensor([[left0exp,right0exp]...]).
    def forward(self, x, y):
        x = x.to(device).unsqueeze(1)
        y = y.to(device).unsqueeze(1)

        x = self.conv1(x)
        x = self.bn1(x)
        x = F.relu(x)
        y = F.relu(y)

        x = torch.flatten(x, 1)
        y = torch.flatten(y, 1)
        x = torch.cat((x, y), 1)

        x = self.head(x)
        return x