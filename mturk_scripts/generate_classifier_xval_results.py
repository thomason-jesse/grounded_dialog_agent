#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../')  # necessary to import KBGrounder from above directory
sys.path.append('../../tsp')

import argparse
import pickle
import KBGrounder
import PerceptionClassifiers


def main():

    # Load parameters from command line.
    parser_fn = FLAGS_parser_fn
    kb_static_facts_fn = FLAGS_kb_static_facts_fn
    kb_perception_source_dir = FLAGS_kb_perception_source_dir
    kb_perception_feature_dir = FLAGS_kb_perception_feature_dir
    active_test_set = [str(oidx) for oidx in FLAGS_active_test_set.split(',')]

    # Instantiate a grounder.
    with open(parser_fn, 'rb') as f:
        p = pickle.load(f)
    g = KBGrounder.KBGrounder(p, kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir,
                              active_test_set)

    # For every predicate, calculate the cross-validation performance.
    sum_pk = 0
    sum_no = 0
    sum_p = 0
    sum_nomv_pk = 0
    sum_nomv_no = 0
    sum_nomv_p = 0
    print("PRED:\tKAPPA\t(#OBJS)\t[[TN, FP], [FN, TP]]")
    for p in g.kb.perceptual_preds:
        pidx = g.kb.perceptual_preds.index(p)
        cm = [[0, 0], [0, 0]]
        num_labeled_objs = 0
        for oidx in range(32):
            if oidx in active_test_set:
                continue

            # Blind the perception classifier to this oidx, get annotator label, and retrain classifier.
            old_labels = g.kb.pc.labels[:]
            g.kb.pc.labels = [lt for lt in g.kb.pc.labels if lt[0] != pidx or lt[1] != oidx]
            vote_sum = sum([1 if lt[2] else -1
                            for lt in old_labels if lt[0] == pidx and lt[1] == oidx])
            if vote_sum == 0:  # annotators do not agree on label
                continue
            vote = 1 if vote_sum > 0 else 0
            g.kb.pc.train_classifiers([pidx])

            # Get held-out result nad update the appropriate cell in the confusion matrix.
            pos_conf, neg_conf = g.kb.pc.run_classifier(pidx, oidx)
            if pos_conf > neg_conf:
                predicted = 1
            else:
                predicted = 0
            cm[vote][predicted] += 1
            num_labeled_objs += 1

        # Get predicate signed kappa.
        if num_labeled_objs > 1:
            pk = PerceptionClassifiers.get_signed_kappa(cm)
            print(str(p) + ":\t" + str(pk) + "\t(" + str(num_labeled_objs) + ")\t" + str(cm))

            # Track.
            sum_pk += pk
            sum_no += num_labeled_objs
            sum_p += 1
            if cm[0][0] + cm[1][0] != num_labeled_objs and cm[0][1] + cm[1][1] != num_labeled_objs:
                sum_nomv_pk += pk
                sum_nomv_no += num_labeled_objs
                sum_nomv_p += 1

    # Averages.
    if sum_p > 0:
        print("average:\t" + str(sum_pk / sum_p) + "\t(" + str(float(sum_no) / sum_p) +
              " objs)\t(" + str(sum_p) + " preds)")
    if sum_nomv_p > 0:
        print("average (non-majority vote):\t" + str(sum_nomv_pk / sum_nomv_p) +
              "\t(" + str(float(sum_nomv_no) / sum_nomv_p) + " objs)\t(" + str(sum_nomv_p) + " preds)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parser_fn', type=str, required=True,
                        help="parser infile")
    parser.add_argument('--kb_static_facts_fn', type=str, required=True,
                        help="static facts file for the knowledge base")
    parser.add_argument('--kb_perception_source_dir', type=str, required=True,
                        help="perception source directory for knowledge base")
    parser.add_argument('--kb_perception_feature_dir', type=str, required=True,
                        help="perception feature directory for knowledge base")
    parser.add_argument('--active_test_set', type=str, required=True,
                        help="objects to consider possibilities for grounding; " +
                             "excluded from perception classifier training")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
