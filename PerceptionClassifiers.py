#!/usr/bin/env python
__author__ = 'jesse'

import numpy as np
import os
import pickle
from sklearn.svm import SVC


class PerceptionClassifiers:

    def __init__(self, source_dir, feature_dir, active_test_set, kernel='linear'):
        debug = False

        # Initialization parameters.
        self.source_dir = source_dir  # str; expects predicates.pickle, labels.pickle for object/pred relationships
        self.feature_dir = feature_dir  # str; expects oidxs.pickle, features.pickle for objects
        self.active_test_set = active_test_set  # list of int; oidxs' labels to be excluded from SVM training/test
        self.kernel = kernel  # str

        self.predicates = None  # list of strs
        self.oidxs = None  # list of ints
        self.labels = None  # list of (pidx, oidx, label) triples for label in {False, True}
        self.features = None  # list of behavior, modality indexed dictionaries into lists of observation vectors
        self.behaviors = None  # list of strs
        self.contexts = None  # list of (behavior, modality) str tuples
        self.classifiers = None  # list of behavior, modality indexed dictionaries into SVC classifiers
        self.kappas = None  # list of behavior, modality indexed dictionaries into [0, 1] floats
        self.weights = None  # list of behavior, modality indexed dictionaries into [0, 1] confidences summing to 1

        self.classifiers_fn = "classifiers_" + '_'.join([str(oidx) for oidx in active_test_set]) + ".pickle"
        if debug:
            print "classifiers_fn = " + self.classifiers_fn

        # Read in source information.
        if debug:
            print "reading in source information..."
        predicate_fn = os.path.join(self.source_dir, "predicates.pickle")
        if os.path.isfile(predicate_fn):
            with open(predicate_fn, 'rb') as f:
                self.predicates = pickle.load(f)
        else:
            print ("WARNING: python_classifier_services unable to load " +
                   str(predicate_fn) + "; starting with blank predicate list")
            self.predicates = []
        labels_fn = os.path.join(self.source_dir, "labels.pickle")
        if os.path.isfile(labels_fn):
            with open(labels_fn, 'rb') as f:
                self.labels = pickle.load(f)
        else:
            print ("WARNING: python_classifier_services unable to load " +
                   str(labels_fn) + "; starting with blank labels list")
            self.labels = []
        with open(os.path.join(self.feature_dir, "oidxs.pickle"), 'rb') as f:
            self.oidxs = pickle.load(f)
        with open(os.path.join(self.feature_dir, "features.pickle"), 'rb') as f:
            self.features = pickle.load(f)
        self.behaviors = ["drop", "grasp", "hold", "lift", "look", "lower", "press", "push"]
        self.modalities = ["audio", "color", "fpfh", "haptics", "fc7"]
        self.contexts = []
        for b in self.behaviors:
            self.contexts.extend([(b, m) for m in self.modalities
                                  if m in self.features[self.oidxs[0]][b].keys()])
        if debug:
            print "... done"

        # Read in cashed classifiers or train fresh ones.
        classifier_fn = os.path.join(source_dir, self.classifiers_fn)
        if os.path.isfile(classifier_fn):
            if debug:
                print "reading cached classifiers from file..."
            with open(classifier_fn, 'rb') as f:
                self.classifiers, self.kappas = pickle.load(f)
                self.weights = [self.get_weight_from_kappa(pidx) for pidx in range(len(self.predicates))]
        else:
            if debug:
                print "training classifiers from source information..."
            self.classifiers = [None for _ in range(len(self.predicates))]  # pidx, b, m
            self.kappas = [{b: {m: 0 for _b, m in self.contexts if b == _b}
                            for b in self.behaviors}
                           for _ in range(len(self.predicates))]
            self.weights = [self.get_weight_from_kappa(pidx) for pidx in range(len(self.predicates))]
            self.train_classifiers(range(len(self.predicates)))
        if debug:
            print "... done"

    # Given a predicate idx, get the normalized weights based on kappas for that predicate
    def get_weight_from_kappa(self, pidx):
        s = sum([self.kappas[pidx][b][m] for b, m in self.contexts])
        return {b: {m: self.kappas[pidx][b][m] / float(s) if s > 0 else 1.0 / len(self.contexts)
                for _b, m in self.contexts if b == _b} for b in self.behaviors}

    # Gets the result of specified predicate on specified object.
    # Takes in a predicate idx and object idx
    # Returns a tuple of pos_conf, neg_conf for confidence in [0, 1] that the label does or does not apply
    # pos_conf + neg_conf = 1.0 unless pos_conf = neg_conf = 0
    def run_classifier(self, pidx, oidx):
        debug = False

        # Check existing labels.
        ls = [l for _p, _o, l in self.labels if _p == pidx and _o == oidx and _o not in self.active_test_set]
        if len(ls) > 0:
            # This object is already labeled.
            if debug:
                print ("returning Laplace-1 smoothed class balance for seen pred '" + self.predicates[pidx] +
                       "' on object " + str(oidx))
            pos_conf = (1 + ls.count(1)) / float(len(ls) + 2)
            neg_conf = (1 + ls.count(0)) / float(len(ls) + 2)
        else:

            # Run classifiers if trained.
            if self.classifiers[pidx] is not None:
                if debug:
                    print "running classifier '" + self.predicates[pidx] + "' on object " + str(oidx)
                pos_conf = 0
                neg_conf = 0
                for b, m in self.contexts:
                    x, y, z = get_classifier_results(self.classifiers[pidx][b][m], b, m,
                                                     [(oidx, None)], self.features, self.kernel, None)
                    for v in z:
                        if v == 1:
                            pos_conf += self.weights[pidx][b][m] / float(len(z))
                        elif v == -1:
                            neg_conf += self.weights[pidx][b][m] / float(len(z))
            else:
                if debug:
                    print "classifier '" + self.predicates[pidx] + "' is untrained"
                pos_conf = 0.5  # confidences are equally uncertain
                neg_conf = 0.5

        # Prepare and send response.
        if debug:
            print "... returning pos_conf " + str(pos_conf) + " and neg_conf " + str(neg_conf)
        return pos_conf, neg_conf

    # Updates the in-memory classifiers given new labels in the request.
    # Takes new_preds which will extend existing list, pidxs a list of predicate idxs,
    # oidxs a list of object idxs, and labels a list of labels corresponding in parallel
    # to the pidx, oidx combinations
    def update_classifiers(self, upreds, upidxs, uoidxs, ulabels):
        debug = False

        assert len(upidxs) == len(uoidxs) and len(uoidxs) == len(ulabels)
        if debug:
            print ("updating classifiers with new preds " + str(upreds) + " and triples " +
                   str([(upidxs[idx], uoidxs[idx], ulabels[idx]) for idx in range(len(upidxs))]))
        self.predicates.extend(upreds)
        for _ in range(len(upreds)):
            self.classifiers.append(None)
            self.kappas.append({b: {m: 0 for _b, m in self.contexts if b == _b}
                                for b in self.behaviors})
            self.weights.append(self.get_weight_from_kappa(len(self.kappas)-1))
        retrain_pidxs = []
        for idx in range(len(upidxs)):
            pidx = upidxs[idx]
            if pidx not in retrain_pidxs:
                retrain_pidxs.append(pidx)
            self.labels.append((pidx, uoidxs[idx], ulabels[idx]))
        self.train_classifiers(retrain_pidxs)

    # Commits the trained classifiers and current labels to the classifier and source directories, respectively.
    def commit_changes(self):
        debug = False

        if debug:
            print "committing new predicates, labels, and classifiers to disk"
        with open(os.path.join(self.source_dir, "predicates.pickle"), 'wb') as f:
            pickle.dump(self.predicates, f)
        with open(os.path.join(self.source_dir, "labels.pickle"), 'wb') as f:
            pickle.dump(self.labels, f)
        with open(os.path.join(self.source_dir, self.classifiers_fn), 'wb') as f:
            pickle.dump([self.classifiers, self.kappas], f)

    # Get oidx, l from pidx, oidx, l labels.
    def get_pairs_from_labels(self, pidx):
        pairs = []
        for pjdx, oidx, l in self.labels:
            if pjdx == pidx and oidx not in self.active_test_set:
                pairs.append((oidx, 1 if l else -1))
        return pairs

    # Train all classifiers given boilerplate info and labels.
    def train_classifiers(self, pidxs):
        debug = False

        if debug:
            print "training classifiers " + ','.join([self.predicates[pidx] for pidx in pidxs])
        for pidx in pidxs:
            train_pairs = self.get_pairs_from_labels(pidx)
            if -1 in [l for _, l in train_pairs] and 1 in [l for _, l in train_pairs]:
                if debug:
                    print "... '" + self.predicates[pidx] + "' fitting"
                pc = {}
                pk = {}
                for b, m in self.contexts:
                    if b not in pc:
                        pc[b] = {}
                        pk[b] = {}
                    pc[b][m] = fit_classifier(b, m, train_pairs, self.features, self.kernel)
                    pk[b][m] = get_margin_kappa(pc[b][m], b, m, train_pairs, self.features,
                                                self.kernel, xval=train_pairs)
                s = sum([pk[b][m] for b, m in self.contexts])
                for b, m in self.contexts:
                    pk[b][m] = pk[b][m] / float(s) if s > 0 else 1.0 / len(self.contexts)
                self.classifiers[pidx] = pc
                self.kappas[pidx] = pk
                self.weights[pidx] = self.get_weight_from_kappa(pidx)
            else:
                if debug:
                    print "... '" + self.predicates[pidx] + "' lacks a +/- pair to fit"
                self.classifiers[pidx] = None
                self.kappas[pidx] = {b: {m: 0 for _b, m in self.contexts if b == _b}
                                     for b in self.behaviors}
                self.weights[pidx] = self.get_weight_from_kappa(pidx)


# Given an SVM c and its training data, calculate the agreement with gold labels according to kappa
# agreement statistic at the observation level.
def get_margin_kappa(c, behavior, modality, pairs, object_feats, kernel, xval=None):
    x, y, z = get_classifier_results(c, behavior, modality, pairs, object_feats, kernel, xval)
    cm = [[0, 0], [0, 0]]
    for idx in range(len(x)):
        cm[1 if y[idx] == 1 else 0][1 if z[idx] == 1 else 0] += 1
    return get_kappa(cm)


# Given an SVM and its training data, fit that training data, optionally retraining leaving
# one object out at a time.
def get_classifier_results(c, behavior, modality, pairs, object_feats, kernel, xval):
    if c is None:
        x, y = get_data_for_classifier(behavior, modality, pairs, object_feats)
        z = [-1 for _ in range(len(x))]  # No classifier trained, so guess majority class no.
    else:
        if xval is None:
            x, y = get_data_for_classifier(behavior, modality, pairs, object_feats)
            z = c.predict(x)
        else:
            x = []
            y = []
            z = []
            rel_oidxs = list(set([oidx for (oidx, l) in pairs]))
            if len(rel_oidxs) > 1:
                for oidx in rel_oidxs:
                    # Train a new classifier without data from oidx.
                    xval_pairs = [(ojdx, l) for (ojdx, l) in xval if ojdx != oidx]
                    ls = list(set([l for ojdx, l in xval_pairs]))
                    if len(ls) == 2:
                        xval_c = fit_classifier(behavior, modality, xval_pairs, object_feats, kernel)
                    else:
                        xval_c = None

                    # Evaluate new classifier on held out oidx data and record results.
                    xval_pairs = [(ojdx, l) for (ojdx, l) in pairs if ojdx == oidx]
                    _x, _y = get_data_for_classifier(behavior, modality, xval_pairs, object_feats)
                    if xval_c is not None:
                        _z = xval_c.predict(_x)
                    else:  # If insufficient data, vote the same label as the training data.
                        _z = [1 if len(ls) > 0 and ls[0] == 1 else -1 for _ in range(len(_x))]
                    x.extend(_x)
                    y.extend(_y)
                    z.extend(_z)
            else:
                x, y = get_data_for_classifier(behavior, modality, pairs, object_feats)
                z = [-1 for _ in range(len(x))]  # Single object, so guess majority class no.
    return x, y, z


# Fits a new SVM classifier given a kernel, context, training pairs, and object feature structure.
def fit_classifier(behavior, modality, pairs, object_feats, kernel):
    x, y = get_data_for_classifier(behavior, modality, pairs, object_feats)
    assert len(x) > 0  # there is data
    assert min(y) < max(y)  # there is more than one label
    c = SVC(kernel=kernel, degree=2)
    c.fit(x, y)
    return c


# Given a context, label pairs, and object feature structure, returns SVM-friendly x, y training vectors.
def get_data_for_classifier(behavior, modality, pairs, object_feats):
    x = []
    y = []
    for oidx, label in pairs:
        if behavior in object_feats[oidx] and modality in object_feats[oidx][behavior]:
            for obs in object_feats[oidx][behavior][modality]:
                if len(obs) == 1 and type(obs[0]) is list:  # un-nest single observation vectors
                    obs = obs[0]
                x.append(obs)
                l = 1 if label == 1 else -1
                y.append(l)
    return x, y


# Returns non-negative kappa.
def get_kappa(cm):
    return max(0, get_signed_kappa(cm))


# Returns non-negative kappa.
def get_signed_kappa(cm):

    s = float(cm[0][0] + cm[0][1] + cm[1][0] + cm[1][1])
    po = (cm[1][1] + cm[0][0]) / s
    ma = (cm[1][1] + cm[1][0]) / s
    mb = (cm[0][0] + cm[0][1]) / s
    pe = (ma + mb) / s
    kappa = (po - pe) / (1 - pe)
    return kappa
