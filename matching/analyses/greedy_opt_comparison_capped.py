#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb  3 16:49:48 2018

@author: halflearned
"""

from os import system
from random import choice
from sys import platform
from time import time

from matching.environment.abo_environment import ABOKidneyExchange
from matching.environment.optn_environment import OPTNKidneyExchange
from matching.environment.saidman_environment import SaidmanKidneyExchange
from matching.solver.kidney_solver3 import solve_with_time_constraints
from matching.trimble_solver.interface import greedy

if platform == "darwin":
    entry_rate = 5
    death_rate = 0.1
    max_chain = 3
    time_length = 1000
    fraction_ndd = 0.1
    max_cycle = 0
else:
    entry_rate = choice([3, 5, 7])
    death_rate = choice([0.01, 0.05, 0.075, .1, .25, .5])
    max_chain = choice([2, 3, 4])
    max_cycle = 0  # choice([0, 2, 3, 4]) # Cycles not implemented yet
    if max_chain > 0:
        fraction_ndd = choice([0.05, 0.1])
    else:
        fraction_ndd = 0
    time_length = 1000

t = time()

print("Entry:", entry_rate,
      "Death", death_rate,
      "Cycle", max_cycle,
      "Chain", max_chain)

env_params = dict(entry_rate=entry_rate,
                  death_rate=death_rate,
                  time_length=time_length,
                  fraction_ndd=fraction_ndd)


envname, env = choice([
    #("OPTN", OPTNKidneyExchange(entry_rate, death_rate, time_length)),
    ("RSU", SaidmanKidneyExchange(entry_rate, death_rate, time_length)),
    #("ABO", ABOKidneyExchange(**env_params))
])

print("\tSolving optimal with time constraints")
sol = solve_with_time_constraints(env,
                                  max_cycle=0,
                                  max_chain=max_chain)
opt = {"obj": sol.ObjVal}

print("\tSolving greedy")
gre = greedy(env,
           max_cycle=0,
           max_chain=max_chain,
           formulation="hpief_prime_full_red")

t_diff = time() - t
res = [envname,
       env.entry_rate, env.death_rate, env.time_length, fraction_ndd,
       max_cycle, max_chain,
       opt["obj"], gre["obj"],
       gre["obj"] / opt["obj"] if opt["obj"] > 0 else np.nan,
       t_diff]

print(res)

if platform == "linux":
    with open("results/greedy_opt_comparison_results_capped.txt", "a") as f:
        f.write(",".join([str(s) for s in res]) + "\n")

    system("qsub job_comparison.pbs")