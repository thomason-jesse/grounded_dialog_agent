#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../')  # necessary to import KBGrounder from above directory
sys.path.append('../../tsp')

import argparse
import operator
import pickle
import KBGrounder
import os


def main():

    # Load parameters from command line.
    parser_fn = FLAGS_parser_fn
    kb_static_facts_fn = FLAGS_kb_static_facts_fn
    kb_perception_source_dir = FLAGS_kb_perception_source_dir
    kb_perception_feature_dir = FLAGS_kb_perception_feature_dir
    active_train_set = [str(oidx) for oidx in FLAGS_active_train_set.split(',')] \
        if FLAGS_active_train_set is not None else None
    active_test_set = [str(oidx) for oidx in FLAGS_active_test_set.split(',')]
    outfile = FLAGS_outfile

    # Create a new labels.pickle that erases the labels of the active training set for test purposes.
    full_annotation_fn = os.path.join(kb_perception_source_dir, 'full_annotations.pickle')
    if os.path.isfile(full_annotation_fn):
        print("main: creating new labels.pickle that blinds the active training set for this test...")
        with open(full_annotation_fn, 'rb') as f:
            fa = pickle.load(f)
        with open(os.path.join(kb_perception_source_dir, 'labels.pickle'), 'wb') as f:
            labels = []
            for oidx in fa:
                if active_train_set is None or oidx not in active_train_set:
                    for pidx in range(len(fa[oidx])):
                        labels.append((pidx, oidx, fa[oidx][pidx]))
            pickle.dump(labels, f)
    with open(parser_fn, 'rb') as f:
        p = pickle.load(f)
    g = KBGrounder.KBGrounder(p, kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir,
                              active_test_set)

    # Start dumping HTML.
    table_format = "<table border=1px cellspacing=1px cellpadding=1px>"
    with open(outfile, 'w') as f:

        f.write("<p><b>Train object data</b>")
        f.write(table_format + "<tr><th>predicate</th><th>positive</th><th>negative</th></tr>")
        preds = g.kb.perceptual_preds
        w = 3
        for pidx in range(len(preds)):
            print("calculating info for pred '" + preds[pidx] + "'...")
            f.write("<tr><td>" + preds[pidx] + "</td>")

            pairs = []
            oidx_votes = {}
            for pjdx, oidx, l in g.kb.pc.labels:
                if pjdx == pidx and oidx not in g.kb.pc.active_test_set:
                    if oidx not in oidx_votes:
                        oidx_votes[oidx] = []
                    oidx_votes[oidx].append(1 if l else -1)
            for oidx in oidx_votes:
                s = sum(oidx_votes[oidx])
                if s > 0:
                    pairs.append((oidx, 1, oidx_votes[oidx].count(1), oidx_votes[oidx].count(-1)))
                elif s < 0:
                    pairs.append((oidx, -1, oidx_votes[oidx].count(1), oidx_votes[oidx].count(-1)))

            for label in [1, -1]:
                f.write("<td>")
                c = 0
                f.write("<table><tr>")
                for oidx, l, pos_v, neg_v in pairs:
                    if l == label:
                        f.write("<td><img width=\"200px\" height=\"200px\" " +
                                "src=\"../www/images/objects/oidx_" + str(oidx) + ".jpg\">")
                        f.write("<br/>(" + str(pos_v) + ", " + str(neg_v) + ")</td>")
                        c += 1
                        if c == w:
                            f.write("</tr><tr>")
                            c = 0
                f.write("</tr></table>")
                f.write("</td>")
            f.write("</tr>")
        f.write("</table></p>")

        f.write("<hr>")
        f.write("<p><b>Test object results</b>")
        f.write(table_format + "<tr><th>predicate</th>")
        for idx in range(len(active_test_set)):
            f.write("<th>" + str(idx + 1) + "</th>")
        f.write("</tr>")

        # Run each trained classifier on each object in the test set.
        for pidx in range(len(preds)):
            f.write("<tr><td>" + preds[pidx] + "</td>")
            if g.kb.pc.classifiers[pidx] is not None:
                oidx_pos = {}
                for oidx in active_test_set:
                    q = (preds[pidx], "oidx_" + str(oidx))
                    pos, neg = g.kb.query(q)
                    oidx_pos[oidx] = pos
                s = sum([oidx_pos[oidx] for oidx in oidx_pos.keys()])
                oidx_d = {oidx: oidx_pos[oidx] / s if s > 0 else 0 for oidx in oidx_pos.keys()}
                for oidx, pos in sorted(oidx_pos.items(), key=operator.itemgetter(1), reverse=True):
                    f.write("<td><img width=\"200px\" height=\"200px\" " +
                            "src=\"../www/images/objects/oidx_" + str(oidx) + ".jpg\"><br/>conf %.2f" % pos +
                            "<br/>prob %.2f" % oidx_d[oidx] + "</td>")
            else:
                for _ in range(len(active_test_set)):
                    f.write("<td>&nbsp;</td>")
            f.write("</tr>")
        f.write("</table></p>")


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
    parser.add_argument('--active_train_set', type=str, required=False, default=None,
                        help="objects to consider 'local' and able to be queried by opportunistic active learning")
    parser.add_argument('--outfile', type=str, required=False,
                        help="file to write html page to")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
