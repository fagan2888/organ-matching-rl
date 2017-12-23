#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Sep 18 11:28:15 2017


@author: vitorhadad
"""

import torch
from torch import nn, cuda
from torch.autograd import Variable
import torch.nn.functional as F
from torch import optim
import numpy as np


def all_sum(x):
    return x.sum()

use_cuda = cuda.is_available()

def to_var(x, requires_grad = True):
    return Variable(torch.FloatTensor(np.array(x, dtype = np.float32)),
                    requires_grad = requires_grad)


class GCNet(nn.Module):
    
    def __init__(self, 
                 feature_size,
                 hidden_sizes = None,
                 output_size = 2,
                 dropout_prob = 0.2,
                 activation_fn = nn.SELU,
                 output_fn = nn.Sigmoid,
                 opt = optim.Adam,
                 opt_params = dict(lr = 0.001),
                 seed = None):
    
        
        if seed : torch.manual_seed(seed)
        
        super(GCNet, self).__init__()
        
        self.feature_size  = feature_size
        self.hidden_sizes = hidden_sizes or []
        self.output_size = output_size
        
        self.activation_fn = activation_fn
        self.dropout_prob = dropout_prob
        self.output_fn = output_fn()
        
        self.logit_loss_fn = nn.CrossEntropyLoss(reduce = True,
                        weight = torch.FloatTensor([1, 10]))
        self.count_loss_fn = nn.MSELoss()
        
        self.model = self.build_model()
        self.logit_layer = nn.Linear(hidden_sizes[-1], 2)
        self.count_layer = nn.Linear(hidden_sizes[-1], 1)
    
        self.opt=opt(self.parameters(), **opt_params)
        
  
        
    def forward(self, A, X):
        
        A, X = self.make_variables(A, X)
        h = X
        for layer in self.model:
            h = layer(A @ h)
            
        logits = self.logit_layer(h)
        counts = self.count_layer(h.sum(1))
        return logits, counts
    

    def make_variables(self, AA, XX):

        with np.errstate(divide='ignore'):  
            As = []
            for A in AA:
                outdeg = A.sum(1)
                D = np.diag(np.sqrt(safe_invert(outdeg)))
                I = np.eye(A.shape[0])
                Atilde = D @ (I + A) @ D
                As.append(Atilde)   
            As = np.stack(As)
            
        XX = to_var(XX)
        AA = to_var(AA)
        
        return AA, XX
            


    def build_model(self):
        
        layer = lambda inp, out: \
                nn.Sequential(
                    nn.Linear(inp, out),
                    self.activation_fn(),
                    nn.AlphaDropout(self.dropout_prob))
        
        sizes = [ self.feature_size,
                 *self.hidden_sizes]
        
        mlp = [layer(h0,h1) for h0, h1 in zip(sizes[:-1], sizes[1:])]
        
        return nn.Sequential(*mlp)
            
    
    
    def run(self, A, X, y, lengths = None):
        
        if lengths is None:
            lengths = X.any(2).sum(1)
            
        batch_size = X.shape[0]
        ylogits, ycount = self.forward(A, X)
        ytruth = to_var(y, False).long()
        
        # Compute loss, leaving out padded bits      
        logit_loss = 0
        for s,yh,yt in zip(lengths, ylogits, ytruth):
            try:
                logit_loss += self.logit_loss_fn(yh[:s], yt[:s].view(-1)).mean()
            except RuntimeError as e:
                print("RuntimeError", e)
        logit_loss /= batch_size
        
        count_loss = self.count_loss_fn(ycount, ytruth.sum(1).float())
    
        loss = logit_loss + count_loss
        
        #stop = (loss > 10000).data.numpy()[0]
        #if stop:
        #    import pdb; pdb.set_trace()
        
        self.opt.zero_grad()
        loss.backward()
        self.opt.step()
        
        return (logit_loss.data.numpy()[0], 
                count_loss.data.numpy()[0], 
                ylogits, ycount.data.numpy())
    
    
    
    def __str__(self):
        
        if self.hidden_sizes:
            hs = "-".join([str(x) for x in self.hidden_sizes])
        else: 
            hs = "None"
        
        return "GCN_" + hs + \
            "_{:1d}".format(int(100*self.dropout_prob))
    


def pad(A, X, y, size):
    
    if len(A.shape) > 2 or len(X.shape) > 2:
        raise ValueError("A and X must be 2D.")
        
    n = size - X.shape[0]
    y = y.reshape(-1, 1)
    
    if n > 0:
        A = np.pad(A.toarray(), ((0,n),(0,n)), mode = "constant", constant_values = 0) 
        X = np.pad(X, ((0,n),(0,0)), mode = "constant", constant_values = 0)
        y = np.pad(y, ((0,n),(0,0)), mode = "constant", constant_values = 0)    
        
    return A, X, y



safe_invert = lambda x: np.where(x > 0, 1/x, 0)



#%%    
    
if __name__ == "__main__":

    from sys import argv, platform
    from matching.utils.data_utils import open_file, confusion

    batch_size = 32
    open_every = 100
    log_every = 10
    save_every = 500
 
    if platform == "darwin":
        argv = [None, "optn", "3", "100", "True", np.random.randint(1e8)]

    env_type = argv[1]
    hidden = int(argv[3])
    num_layers = int(argv[2])
    use_gn = bool(argv[4])
    s = str(argv[5])
    
    input_size = {"abo":10, "optn":280}
        
    net = GCNet(input_size[env_type] + 14*use_gn, 
                [hidden]*num_layers,
                dropout_prob = .2) 
    
    name = "{}-{}_{}".format(
            str(net),
            env_type,
            s)
    c = .5
    #%%

    for i in range(int(1e8)):
        if i % open_every == 0:
            print("new file!")
            if use_gn:
                A, X, GN, Y = open_file(env_type = env_type,
                                        open_A = True,
                                        open_GN = True)
                Z = np.concatenate([X, GN], 2)
            else:
                A, X, Y = open_file(env_type = env_type,
                                    open_A = True,
                                    open_GN = False)
                Z = X
            
        n = A.shape[0]
        idx = np.random.choice(n, size = batch_size)   
        inputs = (A[idx], Z[idx])
        ytrue = Y[idx]
        lens = inputs[1].any(2).sum(1)
        
        avg_ones = np.hstack([Y[k,:l,0] for k,l in zip(idx, lens)]).mean()
        if avg_ones > 0:
            w = c*1/avg_ones
        
        net.logit_loss_fn = nn.CrossEntropyLoss(reduce = True,
                        weight = torch.FloatTensor([1, w]))
        
        lloss,closs, ylogits, ycount = net.run(*inputs, ytrue)
        cacc = np.mean(ycount.round() == ytrue.sum(1))
        tp, tn, fp, fn = confusion(ylogits, ytrue, lens)
        tpr = tp/(tp+fn)
        tnr = tn/(tn+fp)
        lacc = (tp + tn)/(tp+fp+tn+fn)
        
        if tpr < .1:
            c *= 1.05
        if tnr < .1:
            c *= .95
        
        msg = "{:1.4f},{:1.4f},{:1.4f},"\
                "{:1.4f},{:1.4f},{:1.4f},{:1.4f}"\
                .format(lloss,
                        closs,
                    tpr, # True positive rate
                    tnr, # True negative rate
                    lacc, # Logits accuracy
                    cacc, # Count accuracy
                    w) 
                
        if i % log_every == 0:
            print(msg)
            if platform == "linux":
                with open("results/" + name + ".txt", "a") as f:
                    print(msg, file = f)
        
        if platform == "linux" and i % save_every == 0:
            torch.save(net, "results/" + name)
