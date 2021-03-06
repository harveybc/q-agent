# agent_test_v2:Load a dataset generated by q-datagen for reading the reward per 
#               action  and a dataset generated from MT4 CSV-export.mq4 for simulating
#               the trade strategy. It does NOT  use a model to predict the reward  
#               but takes the training signals directly from que q-datagen dataset.
#               the objective is to test if the reward function and the strategy used 
#               for trding with them is correct in an ideal scenario.

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
import csv
from sklearn import svm

## \class QAgent
## \brief Q-Learning agent that uses an OpenAI gym environment for fx trading 
## estimating for each tick, the optimal SL, TP, and Volume.
class QAgent():    
    ## init method
    ## Loads the validation dataset, loads the pre-trained models
    #  initialize forex environment.
    def __init__(self):
        # First argument is the validation dataset, including headers indicating maximum and minimum per feature
        self.vs_f = sys.argv[1]
        # Second argument is the prefix (including path) for the dcn pre-trained models 
        # for the actions, all modes are files with .svm extention and the prefix is
        # concatenated with a number indicating the action:
        # 0 = Buy/CloseSell/nopCloseBuy
        # 1 = Sell/CloseBuy/nopCloseSell
        # 2 = No Open Buy
        # 3 = No Open Sell
        self.model_prefix = sys.argv[2]
        # third argument is the path of the datasset to be used in the gym environment (not q-datagen generated, without headers) 
        self.env_f = sys.argv[3]
        # initialize gym-forex env (version 4)
        self.test_episodes = []
        self.generation = 0
        self.min_reward = -15
        self.max_reward = 15
        self.episode_score = []
        self.episode_length = []
        self.svr_rbf = svm.SVR(kernel='rbf')
        self.model = [self.svr_rbf] * 4 
        self.raw_action = 0
        self.max_index = 0
        self.vs_data = []
        self.vs_num_ticks = 0
        self.vs_num_columns = 0
        self.obsticks = 30
        # TODO: obtener min y max de actions from q-datagen dataset headers
        self.min_TP = 100
        self.max_TP = 30000
        self.min_SL = 100
        self.max_SL = 30000
        self.min_volume = 0.0
        self.max_volume = 0.1
        self.security_margin = 0.1
        
        # register the gym-forex openai gym environment
        # TODO: extraer obs_ticks como el window_size, desde los headers de  salida de q-datagen
        register(
            id='ForexValidationSet-v1',
            entry_point='gym_forex.envs:ForexEnv6',
            kwargs={'dataset': self.env_f ,'max_volume':self.max_volume, 'max_sl':self.max_SL, 
                    'max_tp':self.max_TP, 'min_sl':self.min_SL,
                    'min_tp':self.min_TP,'obsticks':self.obsticks, 
            'capital':800, 'leverage':100, 'num_features': 14}
        )
        # make openai gym environments
        self.env_v = gym.make('ForexValidationSet-v1')
        # Shows the action and observation space from the forex_env, its observation space is
        # bidimentional, so it has to be converted to an array with nn_format() for direct ANN feed. (Not if evaluating with external DQN)
        print("action space: {0!r}".format(self.env_v.action_space))
        print("observation space: {0!r}".format(self.env_v.observation_space))
        # read normalization maximum and minimum per feature
        # n_data_full = genfromtxt(self.vs_f, delimiter=',',dtype=str,skip_header=0)    
        with open(self.vs_f, newline='') as f:
            reader = csv.reader(f)
            n_data = next(reader)  # gets the first line
        # read header from vs_f
        #n_data = n_data_full[0].tolist()
        self.num_columns = len(n_data)
        print("vs_f num_columns = ", self.num_columns)
        # minimum and maximum per feature for normalization before evaluation in pretrained models
        self.max = [None] * self.num_columns
        self.min = [None] * self.num_columns
        for i in range(0, self.num_columns-4):
            header_cell = n_data[i]
            #print("header_cell = ", header_cell, "type = " ,type(header_cell))
            data = header_cell.split("_")
            num_parts = len(data)
            self.max[i] = float(data[num_parts-1])
            self.min[i] = float(data[num_parts-2])
            # data was mormalized as: my_data_n[0, i] = (2.0 * (my_data[0, i] - min[i]) / (max[i] - min[i])) - 1
        
    ## the action model is the same q-datagen generated dataset
    def load_action_models(self):
        for i in range(0,4):
            self.model[i] = load(self.model_prefix + str(i) + '.svm') 
        # load headers from q-datagen output
        self.vs_data = genfromtxt(self.vs_f, delimiter=',')
        # get the number of observations
        self.vs_num_ticks = len(self.vs_data)
        self.vs_num_columns = len(self.vs_data[0])

    ## For an observation for each tick, returns the TP, SL, volume ands direction(+1 buy, -1 sell) of an optimal order. 
    def decide_next_action(self, normalized_observation):
        # evaluate all models with the observion data window 
        self.action_list = []
        vs = np.array(normalized_observation)
        vs_r = np.reshape(vs, (1, -1))
        for i in range(0,4):
            predicted = self.model[i].predict(vs_r)
            #print ("predicted=",predicted)
            self.action_list.append(predicted[0])
        
        self.action = self.action_list.copy()
        return self.action

    ## normalize the observation matriz, converts it to a list feedable to a pretrained SVM
    # oldest data is first in dataset and also in observation matrix
    def normalize_observation(self, observation):
        # observation is a list with size num_features of numpy.deque of size 30 (time window) 
        n_obs = []
        num_columns_o = len(observation)
        #print("num_columns_o = ", num_columns_o)
        # compose list from observation matrix similar to a row of the training set output from q-datagen (tick contiguous per feature)
        for i in range (0, num_columns_o):
            l_obs = list(observation[i])   
            for j in l_obs:
                n_obs.append(j)
        #print("n_obs_pre = ", n_obs)
        for c,i in enumerate(n_obs):
            #if c < 98:
            #print("c=",c," i=",i ," min[",c,"]=",self.min[c]," max[",c,"]=",self.max[c])
            n_obs[c]=((2.0 * (i - self.min[c]) / (self.max[c] - self.min[c])) - 1)
        #print("n_obs_post = ", n_obs)
        return n_obs
    ## Function transform_action: convert the output of the raw_action into the
    ## denormalized values to be used in the simulation environment.
    ## increase the SL in the sec_margin% and decrease the TP in the same %margin, volume is also reduced in the %margin  
    def transform_action(self, order_status, raw_action):
        # raw_action depends on order_status:  0 nop, -1=sell,1=buy
        # the output actions are: 0=TP,1=SL,2=volume(dInv). 
        # if there is no opened order
        act = []
        # initialize values for next order , dir: 1=buy, -1=sell, 0=nop
        dir = 0
        tp = 0
        sl = 0
        vol  = 0.0
        if order_status == 0:
            # if TP, SL, dInv and direction son positivos, retorna los valores ajustados con el margen para buy order
            if (self.raw_action[0] > 0) and (self.raw_action[0] > 0) and (self.raw_action[2] > 0) and (self.raw_action[3] > 0):
                # opens buy order  
                dir = 1
                # TP
                if self.raw_action[0] > 1:
                    tp = (1 - self.security_margin)
                else:
                    tp = self.raw_action[0] * (1 - self.security_margin)
                # SL TODO:PROBANDO CON SL = TP POR dificultad para predecir este valor
                if self.raw_action[1] > 1:
                    sl = (1 + self.security_margin)
                    sl = tp
                else:
                    sl = self.raw_action[1] * (1 + self.security_margin)
                    sl = tp
                # Volume
                if self.raw_action[2] > 1:
                    vol = (1 - self.security_margin)
                else:
                    vol = self.raw_action[2] * (1 - self.security_margin)
                
            # if TP, SL, dInv and direction son negativos, retorna los valores ajustados con el margen para sell order
            if (self.raw_action[0] < 0) and (self.raw_action[0] < 0) and (self.raw_action[2] < 0) and (self.raw_action[3] < 0):
                # opens sell order  
                dir = -1
                # TP
                if self.raw_action[0] < -1:
                    tp = (1 - self.security_margin)
                else:
                    tp = dir * self.raw_action[0] * (1 - self.security_margin)
                # SL
                if self.raw_action[1] < -1:
                    sl = (1 + self.security_margin)
                    # TODO: Prueba
                    sl = tp
                else:
                    sl = dir * self.raw_action[1] * (1 + self.security_margin)
                    # TODO: Prueba
                    sl = tp
                # Volume
                if self.raw_action[2] < -1:
                    vol = (1 - self.security_margin)
                else:
                    vol = dir * self.raw_action[2] * (1 - self.security_margin)
 # TODO: by setting the following to an unreachable condition 2.0, only allow close by sl/tp                       
        if order_status == 1:
            # if TP, SL, dInv or direction son negativos, retorna los valores ajustados con el margen para sell order
            if (self.raw_action[0] < 0) and (self.raw_action[0] < 0) and (self.raw_action[2] < 0) and (self.raw_action[3] < 0):
                # closes buy order  
                dir = -1
                # TP
                if self.raw_action[0] < -1:
                    tp = (1 - self.security_margin)
                else:
                    tp = dir * self.raw_action[0] * (1 - self.security_margin)
                # SL
                if self.raw_action[1] < -1:
                    sl = (1 + self.security_margin)
                else:
                    sl = dir * self.raw_action[1] * (1 + self.security_margin)
                # Volume
                if self.raw_action[2] < -1:
                    vol = (1 - self.security_margin)
                else:
                    vol = dir * self.raw_action[2] * (1 - self.security_margin)
 # TODO: by setting the following to an unreachable condition -2.0, only allow close by sl/tp                   
        if order_status == -1:
            # if TP, SL, dInv and direction son positivos, retorna los valores ajustados con el margen para buy order
            if (self.raw_action[0] > 0) and (self.raw_action[0] > 0) and (self.raw_action[2] > 0) and (self.raw_action[3] > 0):
                # closes sell order  
                dir = 1
                # TP
                if self.raw_action[0] > 1:
                    tp = (1 - self.security_margin)
                else:
                    tp = self.raw_action[0] * (1 - self.security_margin)
                # SL
                if self.raw_action[1] > 1:
                    sl = (1 + self.security_margin)
                else:
                    sl = self.raw_action[1] * (1 + self.security_margin)
                # Volume
                if self.raw_action[2] > 1:
                    vol = (1 - self.security_margin)
                else:
                    vol = self.raw_action[2] * (1 - self.security_margin)    
            
            
        # Create the action list output [tp, sl, vol, dir]
        act.append(tp)
        act.append(sl)
        act.append(vol)  
        act.append(dir)
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
        #print("observation = ", observation)
        normalized_observation = agent.normalize_observation(observation) 
        #print("normalized_observation = ", normalized_observation)
        score = 0.0
        step = 0
        order_status=0
        while 1:
            step += 1
            self.raw_action = self.decide_next_action(normalized_observation)
            action = self.transform_action(order_status, self.raw_action)
            # print("raw_action=", raw_action, " action=", action,)
            # TODO: verificar que datos usados en training sean inguales a los usados en evaluate()
            #       verificar primera fila de pretrainer ts y primera fila que se envía a svm en evaluate()
            #       comparar que ambas predicciones den los mismos valores para las 4 acciones
            # TODO: probar con DCN
            # TODO: exportar plots de pre-trainer como imagenes
            # TODO: verificar que fórmulas para cada action reward son correctas, haciendo 
            #       modelo pre-entrenado que retorna para cada lecctura los valores exáctos de 
            #       reward de cada acción basado en tabla de training apra simular mejor caso
            #if step > 1:
            #    print("a=", action, " order_status=",info['order_status'], " num_closes=", info['num_closes']," balance=",info['balance'], " equity=", info['equity'])
            observation, reward, done, info = self.env_v.step(action)
            order_status=info['order_status']
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
    agent.load_action_models()
    agent.evaluate()