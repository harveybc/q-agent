# agent_svm:    load a set of pretrained svm to estimate the reward of each action
#               to perform and use the most rewarding action in an Gym forex
#               broker acccount simulation environment step

import gym
import gym.wrappers
import gym_forex
from gym.envs.registration import register
import sys
import neat
import os
from joblib import load
from sklearn import svm
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error
import operator
from numpy import genfromtxt

## \class QAgent
## \brief Q-Learning agent that uses an OpenAI gym environment for fx trading 
##  This agent has separate networks (Pre-trained DeepConvNets) for estimating 
##  each action per step of the simulation environment.
class QAgent():    
    ## init method
    ## Loads the validation dataset, loads the pre-trained models
    #  initialize forex environment.
    def __init__(self):
        # First argument is the validation dataset 
        self.vs_f = sys.argv[1]
        # Second argument is the prefix (including path) for the dcn pre-trained models 
        # for the actions, all modes are files with .svm extention and the prefix is
        # concatenated with a number indicating the action:
        # 0 = Buy/CloseSell/nopCloseBuy
        # 1 = Sell/CloseBuy/nopCloseSell
        # 2 = No Open Buy
        # 3 = No Open Sell
        self.model_prefix = sys.argv[2]
        # initialize gym-forex env (version 4)
        self.test_episodes = []
        self.generation = 0
        self.min_reward = -15
        self.max_reward = 15
        self.episode_score = []
        self.episode_length = []
        # register the gym-forex openai gym environment
        register(
            id='ForexValidationSet-v1',
            entry_point='gym_forex.envs:ForexEnv5',
            kwargs={'dataset': self.vs_f,'volume':0.2, 'sl':2000, 'tp':2000,'obsticks':30, 'capital':10000, 'leverage':100}
        )
        # make openai gym environments
        self.env_v = gym.make('ForexValidationSet-v1')
        # Shows the action and observation space from the forex_env, its observation space is
        # bidimentional, so it has to be converted to an array with nn_format() for direct ANN feed. (Not if evaluating with external DQN)
        print("action space: {0!r}".format(self.env_v.action_space))
        print("observation space: {0!r}".format(self.env_v.observation_space))
        # read normalization maximum and minimum per feature
        n_data = genfromtxt(csv_f, delimiter=',')
        num_ticks = len(n_data)
        self.num_columns = len(my_data[0])
        for i in range(0, self.num_columns-4):
            header_cell = n_data[0,i] 
            data = header_cell.split("_")
            num_parts = len(data)
            self.max[i] = float(data[num_parts-1])
            self.min[i] = float(data[num_parts-2])
            # data was mormalized as: my_data_n[0, i] = (2.0 * (my_data[0, i] - min[i]) / (max[i] - min[i])) - 1
        
    ## Load  pretrained models
    def load_action_models(self):
        for i in range(0,4):
            self.model[i] = load(self.svr_rbf, self.model_prefix + str(i) + '.svm') 
        
    ## Evaluate all the action models and select the one with most predicted reward given a marix of historic data as oobsevation
    def decide_next_action(self, normalizd_observation):
        # evaluate all models with the observion data window  
        for i in range(0,4):
            action[i] = self.model[i].predict(normalizd_observation)
        max_value = max(action)
        max_index = action.index(max_value)
        return max_index
    
    ## normalize the observation matriz, converts it to a list feedable to a pretrained SVM
    # oldest data is first in dataset and also in observation matrix
    def normalize_observation(self, observation):
        # observation is a list with size num_features of numpy.deque of size 30 (time window) 
        n_obs = []
        for i in range(0, self.num_columns-4):
            for j in observation[i]:
                # convert each queue  to a list and concatenate all lists
                n_obs.append((2.0 * (j - self.min[i]) / (self.max[i] - self.min[i])) - 1)
        return n_obs
    
    def translate_action(self, order_status, raw_action):
        # raw_action depends on order_status:  0 nop, -1=sell,1=buy
        # the possible output actions are: 0=nop,1=buy,2=sell. 
        # if there is no opened order
        if order_status == 0:
            # opens buy order
            if raw_action == 0:
                act = 1
            # opens buy order
            elif raw_action == 1:
                act = 2
            else:
                act = 0
        # if there is an opened sell order
        if order_status == -1:
            # closes sell order
            if raw_action == 0:
                act = 1
            # do not close the sell order
            elif raw_action == 1:
                act = 0
            # TODO: Probar con accion diferente para raw_action 2 y 3
            else:
                act = 0  
        # if there is an opened buy order
        if order_status == 1:
            # do not close the buy order
            if raw_action == 0:
                act = 0
            # close the buy order
            elif raw_action == 1:
                act = 2
            # TODO: Probar con accion diferente para raw_action 2 y 3
            else:
                act = 0  
        return act
    
    ## Evaluate all the steps on the simulation choosing in each step the best 
    ## action, given the observations per tick. 
    ## \returns the final balance and the cummulative reward
    # Posssible actions: 
    # 0 = Buy/CloseSell/nopCloseBuy
    # 1 = Sell/CloseBuy/nopCloseSell
    # 2 = No Open Buy
    # 3 = No Open Sell
    def evaluate(self):
        # calculate the validation set score
        hist_scores = []
        observation = self.env_v.reset()
        normalized_observation = agent.normalize_observation(observation) 
        score = 0.0
        step = 0
        while 1:
            step += 1
            # TODO: verificar estado de orden para seleccionar que accion tomar
            # TODO: es decir, traducir la próxima acción (0-3) a la variable action(buy, sell, nop)
            raw_action = self.decide_next_action(normalized_observation)
            action = self.translate_action(info['order_status'], raw_action)
            observation, reward, done, info = self.env_v.step(action)
            normalized_observation = self.normalize_observation(observation) 
            score += reward
            #env_v.render()
            if done:
                break
        hist_scores.append(score)
        avg_score = sum(hist_scores) / len(hist_scores)
        print("Validation Set Score = ", avg_score)
        print("*********************************************************")
        return avg_score     

    def show_results(self):
        test=0

# main function 
if __name__ == '__main__':
    agent = QAgent()
    agent.load_action_models(self)
    agent.evaluate()