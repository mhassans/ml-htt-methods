import random
import uproot
import ROOT
import xgboost as xgb
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pickle
import argparse
from scipy import interp
from root_numpy import array2root
import json
from pandas.core.groupby import GroupBy
# import seaborn as sns
from mlglue.tree import tree_to_tmva, BDTxgboost, BDTsklearn
import xgboost2tmva

from sklearn.utils import class_weight
from sklearn.metrics import classification_report
from sklearn.metrics import roc_auc_score
from sklearn.metrics import roc_curve
from sklearn.metrics import auc
from sklearn.metrics import recall_score
from sklearn.metrics import precision_score
from sklearn.model_selection import train_test_split
from sklearn.model_selection import StratifiedKFold
from pandas.plotting import scatter_matrix
from sklearn.metrics import confusion_matrix
from sklearn.preprocessing import StandardScaler

# custom modules
import plot_functions as pf
import load_functions as lf
import fit_functions as ff


parser = argparse.ArgumentParser()

parser.add_argument('-s', action='store_true', default=False,
        dest='skip', help='skip training procedure (default False)')
parser.add_argument('--mode', action='store', default='sklearn_ttsplit',
        help='training procedure (default train_test_split)')
parser.add_argument('--channel', action='store', default='mt',
        help='channels to train on')
parser.add_argument('--sig_sample', action='store', default='powheg',
        help='''ggh signal sample to run on (default powheg)\n
        choose powheg for n_jets < 2 | (n_jets >= 2 & mjj < 300)\n
        choose JHU for n_jets >=2 & mjj > 300''')

opt = parser.parse_args()


print '\nTraining model on {} channel with {} sig samples\n'.format(opt.channel, opt.sig_sample)
sig_files = lf.load_files('./filelist/sig_{}_files.dat'.format(opt.sig_sample))
bkg_files = lf.load_files('./filelist/bkgs_files.dat')
data_files = lf.load_files('./filelist/{0}_data_files.dat'.format(opt.channel))

# this file contains information about the xsections, lumi and event numbers
params_file = json.load(open('Params_2016_smsummer16.json'))
lumi = params_file['MuonEG']['lumi']

# cut_features will only be used for preselection
# and then dropped again
if opt.channel == 'tt':
    cut_features = [
            'mva_olddm_medium_1', 'mva_olddm_medium_2',
            'mva_olddm_loose_1', 'mva_olddm_loose_2',
            'antiele_1', 'antimu_1', 'antiele_2', 'antimu_2',
            'leptonveto', 'trg_doubletau',
            'mjj',
            ]

elif opt.channel == 'mt':
    cut_features = [
            'iso_1',
            'mva_olddm_medium_2',
            'antiele_2', 'antimu_2',
            'leptonveto',
            'trg_singlemuon', 'trg_mutaucross',
            'os', 'mjj'
            ]

elif opt.channel == 'et':
    cut_features = [
            'iso_1',
            'mva_olddm_medium_2',
            'antiele_2', 'antimu_2',
            'leptonveto',
            'trg_singleelectron',
            'os', 'mjj'
            ]

elif opt.channel == 'em':
    cut_features = [
            'iso_1',
            'iso_2',
            'leptonveto',
            'trg_muonelectron',
            'os', 'mjj'
            ]

# features to train on
# apart from 'wt' - this is used for weights
# still need to multipy 'wt' by the scaling factor
# coming from the xsection
features = [
        'pt_1', 'pt_2', 'eta_1', 'eta_2', 'dphi',
        'mt_1', 'mt_2', 'mt_lep',
        'm_vis', 'm_sv', 'pt_tt', 'eta_tt',
        'met', 'met_dphi_1', 'met_dphi_2',
        'n_jets', 'n_bjets',
        'wt',
        'pt_vis',
        ]
if opt.channel == 'em':
    features.append('pzeta')

# directory of the files (usually /vols/cms/)
path = '/vols/cms/akd116/Offline/output/SM/2018/Feb21/'

ggh = []
for sig in sig_files:
    print sig
    sig_tmp = lf.load_mc_ntuple(
            path + sig + '_{}_2016.root'.format(opt.channel),
            'ntuple',
            features,
            opt.sig_sample,
            opt.channel,
            cut_features,
            apply_cuts=False
            )
    ## need to multiply event weight by
    ## (XS * Lumi) / #events
    xs_tmp = params_file[sig]['xs']
    events_tmp = params_file[sig]['evt']
    sig_tmp['wt'] = sig_tmp['wt'] * (xs_tmp * lumi)/events_tmp
    sig_tmp['process'] = sig

    ggh.append(sig_tmp)

ggh = pd.concat(ggh, ignore_index=True)


# pf.plot_correlation_matrix(
#         ggh.drop(['wt'], axis=1),
#         'ggh_{}_{}_correlation_matrix.pdf'.format(opt.channel, opt.sig_sample))

bkgs_tmp = []
for bkg in bkg_files:
    print bkg
    bkg_tmp = lf.load_mc_ntuple(
            path + bkg + '_{}_2016.root'.format(opt.channel),
            'ntuple',
            features,
            opt.sig_sample,
            opt.channel,
            cut_features,
            apply_cuts=False
            )
    ## need to multiply event weight by
    ## (XS * Lumi) / #events
    xs_tmp = params_file[bkg]['xs']
    events_tmp = params_file[bkg]['evt']
    bkg_tmp['wt'] = bkg_tmp['wt'] * (xs_tmp * lumi)/events_tmp

    bkg_tmp['process'] = bkg
    bkgs_tmp.append(bkg_tmp)

bkgs = pd.concat(bkgs_tmp, ignore_index=True)

qcd_tmp = []
for data in data_files:
    print data
    data_tmp = lf.load_data_ntuple(
            path + data + '_{}_2016.root'.format(opt.channel),
            'ntuple',
            features,
            opt.sig_sample,
            opt.channel,
            cut_features,
            apply_cuts=False
            )

    data_tmp['process'] = data
    qcd_tmp.append(data_tmp)
qcd = pd.concat(qcd_tmp, ignore_index=True)

# full background DataFrame
bkgs = pd.concat([bkgs, qcd], ignore_index=True)


# pf.plot_signal_background(
#         ggh, bkgs, 'm_sv',
#         opt.channel, opt.sig_sample,
#         bins=100
        # )

# pf.plot_roc_cutbased(ggh, bkgs, 'm_sv', opt.channel, opt.sig_sample)

# pf.plot_correlation_matrix(
#         bkgs.drop(['wt'], axis=1),
#         'bkgs_{}_{}_correlation_matrix.pdf'.format(opt.channel, opt.sig_sample))

y_sig = pd.DataFrame(np.ones(ggh.shape[0]))
y_bkgs = pd.DataFrame(np.zeros(bkgs.shape[0]))
y = pd.concat([y_sig, y_bkgs])
y.columns = ['class']


### COMMENT OUT IF WANNA
### TRY USING scale_pos_weight INSTEAD OF CLASS_WEIGHTS
# class_weights = class_weight.compute_class_weight(
#         'balanced',
#         np.unique(np.array(y).ravel()),
#         np.array(y).ravel()
#         )

# bkgs['wt'] = bkgs['wt'] * class_weights[0]
# ggh['wt'] = ggh['wt'] * class_weights[1]


X = pd.concat([ggh, bkgs])
X['deta'] = np.abs(X['eta_1'] - X['eta_2'])
X['class'] = y.values

w = np.array(X['wt'])

# columns = X.columns
# Xscaler = StandardScaler()
# np_scaled = Xscaler.fit_transform(X.as_matrix())
# Xscaled = pd.DataFrame(np_scaled)
# Xscaled.columns = columns
# print Xscaled


# X = X.drop(['wt'], axis=1).reset_index(drop=True)



# pf.plot_correlation_matrix(X, 'correlation_matrix.pdf')

## Just some test to correct scatter_matrix


if not opt.skip:
    params = {}


############ SKLEARN WRAPPER ###########

    if opt.mode == 'sklearn_ttsplit':

        ff.fit_ttsplit(X, opt.channel, opt.sig_sample)

    if opt.mode == 'sklearn_sssplit':

        ff.fit_sssplit(X, 4, opt.channel, opt.sig_sample)

    if opt.mode == 'gbc_ttsplit':

        ff.fit_gbc_ttsplit(X, opt.channel, opt.sig_sample)


if opt.skip:
    with open('skl_{}_{}_xgb.pkl'.format(opt.channel, opt.sig_sample), 'r') as f:
        xgb_clf = pickle.load(f)

    # with open('skl_{}_{}_gbc.pkl'.format(opt.channel, opt.sig_sample), 'r') as f:
    #     gbc_clf = pickle.load(f)


    X = X.drop(['wt', 'class', 'eta_1', 'eta_2'], axis=1).reset_index(drop=True)
    feats = X.columns


    # model = xgb_clf.booster().get_dump()
    # xgboost2tmva.convert_model(model, input_variables=feats, output_xml='xgboost.xml')


    # bdt = BDTxgboost(xgb_clf, feats, ["Background", "Signal"])

    # bdt.to_tmva("xgb_{}_{}.weights.xml".format(opt.channel, opt.sig_sample))

    # bdt = BDTsklearn(gbc_clf, feats, ["Background", "Signal"])

    # bdt.to_tmva("gbc_{}_{}.weights.xml".format(opt.channel, opt.sig_sample))
    # bdt.setup_tmva("gbc_{}_{}.weights.xml".format(opt.channel, opt.sig_sample))

    gb = X.groupby('process')
    df_dict = {x: gb.get_group(x) for x in gb.groups}

    score = []
    for key, value in df_dict.iteritems():
        print key
        value = value.drop(['process'], axis=1)
        score = xgb_clf.predict_proba(value)[:,1]
        score.dtype = [('bdt_score_JHU', np.float32)]
        array2root(
                score,
                '/vols/cms/akd116/Offline/output/SM/2018/Feb23/' + key + '_' + opt.channel + '_2016.root',
                'ntuple',
                mode = 'update'
                )

    # y_predicted = xgb_clf.predict_proba(X)[:,1]
    # y_predicted.dtype = [('bdt_score_{}_{}'.format(opt.channel, opt.sig_sample), np.float32)]

    # array2root(y_predicted, './tmp/{}_{}-prediction.root'.format(opt.channel, opt.sig_sample), 'BDToutput')

