#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../')  # necessary to import KBGrounder from above directory
sys.path.append('../../tsp')

import argparse
import KBGrounder
import PerceptionClassifiers


def get_results_for_behaviors_and_modalities(kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir,
                                             active_test_set, fold_size, behaviors, modalities, debug=True):
    # Instantiate a grounder.
    g = KBGrounder.KBGrounder(None, kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir,
                              active_test_set, behaviors=behaviors, modalities=modalities)

    # For every predicate, calculate the cross-validation performance.
    sum_pk = sum_no = sum_p = 0
    sum_nomv_pk = sum_nomv_no = sum_nomv_p = 0
    sum_trained_pk = sum_trained_no = sum_trained_p = 0
    if debug:
        print("PRED:\tKAPPA\t(#OBJS)\t[[TN, FP], [FN, TP]]")
    available_oidxs = [oidx for oidx in range(32) if oidx not in active_test_set]
    if fold_size == 32 - len(active_test_set):  #i.e., leave-one-out cross validation.
        num_folds = fold_size
        train_folds = []
        for idx in range(len(available_oidxs)):
            train_folds.append([available_oidxs[jdx] for jdx in range(len(available_oidxs)) if jdx != idx])
    else:
        num_folds = (32 - len(active_test_set)) // fold_size
        train_folds = [[available_oidxs[idx + jdx] for jdx in range(fold_size)]
                       for idx in range(num_folds)]
    for p in g.kb.perceptual_preds:
        pidx = g.kb.perceptual_preds.index(p)
        cm = [[0, 0], [0, 0]]
        num_labeled_objs = 0
        for train_fold in train_folds:

            # Blind the perception classifier to these oidxs, get annotator label, and retrain classifier.
            old_labels = g.kb.pc.labels[:]
            g.kb.pc.labels = [lt for lt in g.kb.pc.labels if lt[0] != pidx or lt[1] in train_fold]
            g.kb.pc.train_classifiers([pidx])

            # Get held-out result and update the appropriate cell in the confusion matrix.
            for oidx in available_oidxs:  # e.g., not in the active_test_set
                if oidx not in train_fold:  # not something we trained on just now
                    vote_sum = sum([1 if lt[2] else -1
                                    for lt in old_labels if lt[0] == pidx and lt[1] == oidx])
                    if vote_sum == 0:  # annotators do not agree on label for this oidx, so don't count it in the cm
                        continue
                    vote = 1 if vote_sum > 0 else 0

                    pos_conf, neg_conf = g.kb.pc.run_classifier(pidx, oidx)
                    if pos_conf > neg_conf:
                        predicted = 1
                    else:
                        predicted = 0
                    cm[vote][predicted] += 1
                    num_labeled_objs += 1

            # Re-assign old labels.
            g.kb.pc.labels = old_labels

        # Retrain original classifier.
        g.kb.pc.train_classifiers([pidx])

        # Get predicate signed kappa.
        if num_labeled_objs > 1:
            pk = PerceptionClassifiers.get_signed_kappa(cm)
            if debug:
                print(str(p) + ":\t" + str(pk) + "\t(" + str(num_labeled_objs) + ")\t" + str(cm))

            # Track.
            sum_pk += pk
            sum_no += num_labeled_objs
            sum_p += 1
            if cm[0][0] + cm[1][0] != num_labeled_objs and cm[0][1] + cm[1][1] != num_labeled_objs:
                sum_nomv_pk += pk
                sum_nomv_no += num_labeled_objs
                sum_nomv_p += 1
            if g.kb.pc.classifiers[g.kb.pc.predicates.index(p)] is not None:
                sum_trained_pk += pk
                sum_trained_no += num_labeled_objs
                sum_trained_p += 1

    return sum_pk, sum_no, sum_p, sum_nomv_pk, sum_nomv_no, sum_nomv_p, sum_trained_pk, sum_trained_no, sum_trained_p


def main(args):

    # Load parameters from command line.
    active_test_set = [int(oidx) for oidx in args.active_test_set.split(',')]
    fold_size = args.fold_size if args.fold_size is not None else 1
    assert ((32 - len(active_test_set)) / fold_size) % 1 == 0

    if args.sweep is None or args.sweep == 0:
        behaviors = args.behaviors.split(',') if args.behaviors is not None else None
        modalities = args.modalities.split(',') if args.modalities is not None else None

        sum_pk, sum_no, sum_p, sum_nomv_pk, sum_nomv_no, sum_nomv_p, sum_trained_pk, sum_trained_no, sum_trained_p = \
            get_results_for_behaviors_and_modalities(args.kb_static_facts_fn, args.kb_perception_source_dir,
                                                     args.kb_perception_feature_dir, active_test_set, fold_size,
                                                     behaviors, modalities)

        # Averages.
        if sum_p > 0:
            print("average:\t" + str(sum_pk / sum_p) + "\t(" + str(float(sum_no) / sum_p) +
                  " objs)\t(" + str(sum_p) + " preds)")
        if sum_nomv_p > 0:
            print("average (non-majority pred):\t" + str(sum_nomv_pk / sum_nomv_p) +
                  "\t(" + str(float(sum_nomv_no) / sum_nomv_p) + " objs)\t(" + str(sum_nomv_p) + " preds)")
        if sum_trained_p > 0:
            print("average (trained):\t" + str(sum_trained_pk / sum_trained_p) +
                  "\t(" + str(float(sum_trained_no) / sum_trained_p) + " objs)\t(" + str(sum_trained_p) + " preds)")

    # Perform behavior and modality sweeps to search for best performance.
    else:
        conditions = ["look-color-fpfh",
                      "look-fc7", "look-resnet-pul", "look-resnet",
                      "look-fc7-color-fpfh", "look-resnet-pul-color-fpfh", "look-resnet-color-fpfh",
                      "allb-fc7", "allb-resnet-pul", "allb-resnet",
                      "allb-fc7-color-fpfh", "allb-resnet-pul-color-fpfh", "allb-resnet-color-fpfh"]
        print("COND\t\t\t\tK_ALL\tK_NON_MAJ_PRED\tK_TRAINED")
        for c in conditions:
            ps = c.split('-')
            behaviors = ['look'] if 'look' in ps else None
            modalities = ["audio", "haptics"]
            modalities.extend([m for m in ps if m not in ['allb', 'look', 'resnet', 'pul']])
            if 'resnet' in ps:
                if 'pul' in ps:
                    modalities.append('resnet152-pul')
                else:
                    modalities.extend(['resnet152-pul', 'resnet152-fl'])

            sum_pk, sum_no, sum_p, sum_nomv_pk, sum_nomv_no, sum_nomv_p, \
                sum_trained_pk, sum_trained_no, sum_trained_p = \
                get_results_for_behaviors_and_modalities(args.kb_static_facts_fn, args.kb_perception_source_dir,
                                                         args.kb_perception_feature_dir, active_test_set, fold_size,
                                                         behaviors, modalities)

            sp = '\t\t'
            if len(c) < 20:
                sp += '\t'
            print(c + sp + '%.2f' % (sum_pk / sum_p if sum_p > 0 else 0) +
                  '\t%.2f' % (sum_nomv_pk / sum_nomv_p if sum_nomv_p > 0 else 0) +
                  '\t\t%.2f' % (sum_trained_pk / sum_trained_p if sum_trained_p > 0 else 0))
            print(' ' * len(c) + sp + '(' + str(sum_p) + ')\t(' + str(sum_nomv_p) +
                  ')\t\t(' + str(sum_trained_p) + ")")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--kb_static_facts_fn', type=str, required=True,
                        help="static facts file for the knowledge base")
    parser.add_argument('--kb_perception_source_dir', type=str, required=True,
                        help="perception source directory for knowledge base")
    parser.add_argument('--kb_perception_feature_dir', type=str, required=True,
                        help="perception feature directory for knowledge base")
    parser.add_argument('--active_test_set', type=str, required=True,
                        help="objects to consider possibilities for grounding; " +
                             "excluded from perception classifier training")
    parser.add_argument('--behaviors', type=str, required=False,
                        help="specify behaviors to consider")
    parser.add_argument('--modalities', type=str, required=False,
                        help="specify modalities to consider")
    parser.add_argument('--sweep', type=int, required=False,
                        help="if 1, sweep range of behaviors and modalities and report performance diffs")
    parser.add_argument('--fold_size', type=int, required=False,
                        help="number of folds to train; always generalizes from small train -> large test except leave-one-out")
    main(parser.parse_args())
