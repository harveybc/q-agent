# agent_test_v6: Uses RETURN DE MACD ADELANTADO 10 ticks(signal 8 from q-datagen_c_v4) regression signal to decide action 

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
from operator import add,sub
from joblib import dump, load
from sklearn import preprocessing
import random
            
## \class QAgent
## \brief Q-Learning agent that uses an OpenAI gym environment for fx trading 
## estimating for each tick, the optimal SL, TP, and Volume.
class QAgent():    
    ## init method
    ## Loads the validation dataset, loads the pre-trained models
    #  initialize forex environment.
    def __init__(self):
        # percentage of noise to add to an action
        # TODO: cambiar acciones para que solo se cierren ordenes por SL o TP (dep de volatility)
        self.noise = 0.0
        # TODO: probar con órdenes con duración mínima en ticks (solo se puden cerrar por TP/SL y por acttion si se ha superado el min_duartion)
        # noise0, min_duratopn = 0          bal=241k
        # noise0, min_duration = 20         bal=43k
        # noise 0.25, min_duration = 20     bal=1k
        self.duration = 0
        self.min_duration = 1
        # TODO: probar con órdenes que solo se cierran por SL/TP
        # TODO: hacer gridsearch de SL/TP
        # TODO: en caso ideal sin ruido, probar si ganancia incrementa con volumen controlado por volatility
        # TODO: probar si mejora SL/TP controlados por volatilidad respecto a los mejores fijos encontrados por gridsearch
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
        self.num_s = 19
        self.model = [self.svr_rbf] * self.num_s 
        self.raw_action = 0
        self.max_index = 0
        self.vs_data = []
        self.vs_num_ticks = 0
        self.vs_num_columns = 0
        self.obsticks = 30
        # TODO: obtener min y max de actions from q-datagen dataset headers
        self.min_TP = 500
        self.max_TP = 5000
        self.min_SL = 500
        self.max_SL = 1000 
        self.min_volume = 0.0
        self.max_volume = 0.1
        self.security_margin = 0.1
        self.test_action = 0
        # load pre-processing settings
        self.pt = preprocessing.PowerTransformer()
        print("loading pre-processing.PowerTransformer() settings for the generated dataset")
        self.pt = load(self.vs_f+'.powertransformer')
        # load feature-selection mask
        print("loading pre-processing feature selection mask")
        self.mask = load(self.vs_f+'.feature_selection_mask')
        
        # register the gym-forex openai gym environment
        # TODO: extraer obs_ticks como el window_size, desde los headers de  salida de q-datagen
        register(
            id='ForexValidationSet-v1',
            entry_point='gym_forex.envs:ForexEnv6',
            kwargs={'dataset': self.env_f ,'max_volume':self.max_volume, 'max_sl':self.max_SL, 
                    'max_tp':self.max_TP, 'min_sl':self.min_SL,
                    'min_tp':self.min_TP,'obsticks':self.obsticks, 
            'capital':800, 'leverage':100, 'num_features': 13}
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
        for i in range(0, self.num_columns-self.num_s):
            header_cell = n_data[i]
            #print("header_cell = ", header_cell, "type = " ,type(header_cell))
            data = header_cell.split("_")
            num_parts = len(data)
            self.max[i] = float(data[num_parts-1])
            self.min[i] = float(data[num_parts-2])
            # data was mormalized as: my_data_n[0, i] = (2.0 * (my_data[0, i] - min[i]) / (max[i] - min[i])) - 1
        
    def set_dcn_model(self):
        # Deep Convolutional Neural Network for Regression
        model = Sequential()
        # for observation[19][48], 19 vectors of 128-dimensional vectors,input_shape = (19, 48)
        # first set of CONV => RELU => POOL
        # mejor result 0.1 con dropout de 0.4 en 400 epochs con learning rate 0.0002 en config  521,64,32,16, en h4 2018 con indicator_period=70
        # 0.2,0.1,lr=0.0002 1200 eva: 0.117
        # 0.4,eva = 0.108
        model.add(Dropout(0.4,input_shape=(self.num_features,self.window_size)))
        model.add(Conv1D(512, 3))
        model.add(Activation('sigmoid'))
        # Sin batch_normalization daba: 0.204
        # Con batch normalization: e=0.168
        model.add(BatchNormalization())
        # Con dropout = 0.1, e=0.168
        # con dropout = 0.2, e=0.121
        # con dropout = 0.4, e= 0.114
        model.add(Dropout(0.4))
        #sin capa de LSTM50,  e=0.107
        #con capa de LSTM50, e= 0.191
        #model.add(LSTM(units = 50, return_sequences = True))
        
        #model.add(Dropout(0.2))
        # mejor config so far: D0.4-512,D0.2-64,d0.1-32,16d64 error_vs=0.1 con 400 epochs y lr=0.0002
        # sin capa de 64, eva = 0.114
        # on capa de 128, eva = 0.125
        # on capa de 32,  eva = 0.107
        # on capa de 16,  eva = 0.114
        model.add(Conv1D(32, 3))
        model.add(Activation('sigmoid'))
        #model.add(BatchNormalization())

        # con otra capa de 32, eva5 = 0.126
        # sin otra capa de 32, eva5 = 0.107, sin minmax normalization
        # sin otra capa de 32, eva5 = 0.124 , con minmax normalization antes de power transform
        #model.add(Conv1D(32, 3))
        #model.add(Activation('sigmoid'))
        #model.add(BatchNormalization())
        #model.add(Dropout(0.1))
        
        # con capa de 16 da   eva5= 107
        model.add(Conv1D(16, 3))
        model.add(Activation('sigmoid'))
        model.add(BatchNormalization())

        #sin capa de LSTM50, eva3=0.104 probar con 400 epochs
        #con capa de LSTM50, eva3= 0.212
        #model.add(LSTM(units = 50, return_sequences = True))
        
        #model.add(MaxPooling1D(pool_size=2, strides=2))
        # second set of CONV => RELU => POOL
       # model.add(Flatten())  # this converts our 3D feature maps to 1D feature vectors
       # con d=0.1 daba 0.11 con loss=0.08
       # con d=0.2 daba 0.22 con loss=0.06
        model.add(Dense(64, activation='sigmoid', kernel_initializer='glorot_uniform')) # valor óptimo:64 @400k
       # model.add(Activation ('sigmoid'))
        #model.add(BatchNormalization())

        # output layer
        model.add(Flatten())  # this converts our 3D feature maps to 1D feature vectors
        model.add(Dense(1, activation = 'sigmoid'))
        # multi-GPU support
        #model = to_multi_gpu(model)
        #self.reduce_lr = ReduceLROnPlateau(monitor='loss', factor=0.3, patience=5, min_lr=1e-4)
        # use SGD optimizer
        opt = Adamax(lr=self.learning_rate)
        #opt = SGD(lr=self.learning_rate, momentum=0.9)
        #paralell_model = multi_gpu_model(model, gpus=2)
        paralell_model = model
        paralell_model.compile(loss="binary_crossentropy", optimizer=opt, metrics=["accuracy"])
        #model.compile(loss="binary_crossentropy", optimizer="adamax", metrics=["accuracy"])
        #model.compile(loss="mse", optimizer=opt, metrics=["accuracy"])
        return paralell_model

    ## the action model is the same q-datagen generated dataset
    def load_action_models(self):
        self.vs_data = genfromtxt(self.vs_f, delimiter=',')
        # get the number of observations
        self.vs_num_ticks = len(self.vs_data)
        self.vs_num_columns = len(self.vs_data[0])

    ## For an observation for each tick, returns 0 if the slope of the future(10) MACD signal (output 16 zero-based) is negative, 1 if its positive. 
    def decide_next_action(self, normalized_observation):
        # evaluate all models with the observation data window 
        self.action = []
        self.max_index = 0 
        action_list = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]
        vs = np.array(normalized_observation)
        # read the normalized_observation skipping (num_features-1) and sum the values to compare with
        # the sum of the same sum from the validation set.
        a_pattern = 0
        # TODO: ERROR: NO COINCIDEN EL RETURN DE ENTRENAMIENTO CON EL CALCULADO EN NORMALIZE OBS
        num_features = (self.vs_num_columns-self.num_s)//(3*self.obsticks)
        n_p = -1
        for i in range(0, num_features):
            n_p = n_p * -1
            # print("num_features= ",num_features ," len(obs)=",len(normalized_observation), "i=",i)
            if n_p == 1:            
                a_pattern = a_pattern + normalized_observation[self.obsticks * i]
            else:
                #print("len(normalized_observation)=",len(normalized_observation)," i=",i)
                a_pattern = a_pattern * normalized_observation[self.obsticks * i]
        #  for each row of the validation set(output of q-datagen), do the sum and compare with the observation sum
        index = 0
        
        for i in range(1, self.vs_num_ticks):
            a_search = 0
            n_p = -1
            # do the sum of the values per feature to compare with the q-datagen dataset output
            for j in range(0, num_features):
                n_p = n_p * -1
                if n_p == 1:
                    a_search = a_search + self.vs_data[i, self.obsticks * j]
                else:
                    a_search = a_search * self.vs_data[i, self.obsticks * j]
            # Return all values from the action signals
            if (a_pattern == a_search):
                # there are 19 signals and vs_num_columns - 11 is the 8th training signals
                action_list_n = self.vs_data[i, self.vs_num_columns-11 : self.vs_num_columns].copy()
                action_list = action_list_n.tolist()
                break
            else:
                if (i == self.vs_num_ticks-1):
                    print("PATTERN NOT FOUND, i=",i)
        #print("normalized_observation=", normalized_observation)
        #print("a_pattern=", a_pattern, " a_search=", a_search, " index=", i)
        #adds noise to the action 0
        if (random.random()<self.noise):
            if (action_list[0]>0.5):
                action_list[0]=0.0
            else:
                action_list[0]=1.0
        # VOILA!
        self.action = action_list.copy()
        #print("action=",self.action)
        return self.action

    ## normalize the observation matrix, converts it to a list feedable to a pretrained DcN
    # oldest data is first in dataset and also in observation matrix
    # input obs_matrix, prev obs_matrix, output:row
    def normalize_observation(self, observation, observation_prev):
        # observation is a list with size num_features of numpy.deque of size 30 (time window) 
        n_obs = []
        num_columns_o = len(observation)
        #print("num_columns_o = ", num_columns_o)
        # compose list from observation matrix similar to a row of the training set output from q-datagen (tick contiguous per feature)
        for i in range (0, num_columns_o):
            l_obs = list(observation[i])   
            for j in l_obs:
                n_obs.append(j)
        # append list of the returned values 
        # TODO: Cambiar a recorrido de l_obs restando el anterior y solo usar l_obs_prev para el primer elemento
        for i in range (0, num_columns_o):
            l_obs = list(observation[i])   
            l_obs_prev = list(observation_prev[i])   
            # l_dif = l_obs - l_obs_prev
            l_dif = list( map(sub, l_obs, l_obs_prev) )
            for l in l_obs:
                n_obs.append(l)
        #for i in range(0,10):
        #    n_obs.append(0) 
        #apply pre-processing
        n_obs = self.pt.transform(np.array(n_obs).reshape(1,-1))
        n_o = n_obs[0].tolist()
        #print("n_o=",n_o)
        #for i in range(0,9):
        #    n_o.append(0)
        #apply feature selection.
        #print("n_o=",n_o)
        #print("mask=",self.mask)
        #print("len(n_o)=",len(n_o))
        #print("len(mask)", len(self.mask))
        n_obs=np.array(n_o)
        n_obs = n_obs[self.mask]
        return n_obs
    
    ## Function transform_action: convert the output of the raw_action into the
    ## denormalized values to be used in the simulation environment.
    ## increase the SL in the sec_margin% and decrease the TP in the same %margin, volume is also reduced in the %margin  
    def transform_action(self, order_status):
        # order_status:  0 nop, -1=sell,1=buy
        # the variable self.raw_action contains the output of decide_next_action, which is an array of 3 values, MACD signal return, RSI return and MACD main - signal >0?
        # the output actions are: 0=TP,1=SL,2=volume(dInv). 
        # if there is no opened order
        act = []
        # initialize values for next order , dir: 1=buy, -1=sell, 0=nop
        dire = 0.0
        tp = 1.0
        sl = 1.0
        vol  = 1.0
        
        # TODO: if there is an opened order, increases de duration counter, else set it to 0
        if (order_status==0):
            self.duration = 0
        else:
            self.duration = self.duration + 1
        # TODO: add min_duration constraint to evaluate if closing an open order with an action
        # if there is no opened order
        if order_status == 0:
            # si el action[0] > 0, compra, sino vende
            if (self.raw_action[self.test_action] > 0):
                # opens buy order  
                dire = 1.0
            else:
                dire = -1.0
        # if there is an existing buy order
        if (order_status == 1) and (self.duration > self.min_duration):
            # si action[0] == 0 cierra orden de buy 
            if (self.raw_action[self.test_action] <= 0):
                # closes buy order  
                dire = -1.0
        # if there is an existing sell order               
        if (order_status == -1) and (self.duration > self.min_duration):
            # if action[0]>0, closes the sell order
            if (self.raw_action[self.test_action] > 0):
                # closes sell order  
                dire = 1.0
        # Create the action list output [tp, sl, vol, dir]
        act.append(tp)
        act.append(sl)
        act.append(vol)  
        act.append(dire)
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
        normalized_observation = agent.normalize_observation(observation, observation) 
        #print("normalized_observation = ", normalized_observation)
        score = 0.0
        step = 0
        order_status=0
        equity=[]
        balance=[]
        while 1:
            step += 1
            # si el step > 2, hacce el resto, sono usa vector e zeros como accion 
            self.raw_action = self.decide_next_action(normalized_observation)
            action = self.transform_action(order_status)
            observation_prev = observation.copy()
           #if step > 1:
            #    print("a=", action, " order_status=",info['order_status'], " num_closes=", info['num_closes']," balance=",info['balance'], " equity=", info['equity'])
            if (step < 3 ) or (step > (self.vs_num_ticks-self.obsticks)):
                print ("Skippig limits, step = ", step)
                # action = nop
                action = []
                # initialize values for next order , dir: 1=buy, -1=sell, 0=nop
                dire = 0.0
                tp = 1.0
                sl = 1.0
                vol  = 1.0
                # Create the action list output [tp, sl, vol, dir]
                action.append(tp)
                action.append(sl)
                action.append(vol)  
                action.append(dire)
            
            observation, reward, done, info = self.env_v.step(action)
            order_status=info['order_status']
            equity.append(info['equity'])
            balance.append(info['balance'])
            
            # TODO: Hacer gráfico de balance y equity
            normalized_observation = self.normalize_observation(observation, observation_prev)
            score += reward
            #env_v.render() 
            if done:
                break
        lw = 2
        y_rbf = balance
        y_v = equity
        x_seq = list(range(0, len(balance)))
        fig=plt.figure()
        plt.plot(x_seq, y_v, color='darkorange', label='Equity')
        plt.plot(x_seq, y_rbf, color='navy', lw=lw, label='Balance')
        plt.xlabel('tick')
        plt.ylabel('value')
        plt.title('Performance')
        plt.legend()
        fig.savefig('agent_test_8.png')
        #plt.show()
        
        hist_scores.append(score)
        avg_score = sum(hist_scores) / len(hist_scores)
        print("Validation Set Score = ", avg_score)
        print("*********************************************************")
        return info['balance'], avg_score     

    def show_results(self):
        test=0

# main function 
if __name__ == '__main__':
    agent = QAgent()
    #agent.svr_rbf = agent.set_dcn_model()
    agent.load_action_models()
    scores = []
    balances = []
    for i in range(0, 1):
        print("Testing signal ",8+i)
        agent.test_action = i
        agent.load_action_models()
        balance,score = agent.evaluate()
        scores.append(score)
        balances.append(balance)
    print("Results:")
    for i in range(0, 1):
        print("Signal ", 8+i, " balance=",balances[i], " score=",scores[i])
        