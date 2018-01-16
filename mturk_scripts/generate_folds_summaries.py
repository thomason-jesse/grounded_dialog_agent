#!/usr/bin/env python
__author__ = 'jesse'

import argparse
import matplotlib.pyplot as plt
import numpy as np
import os
from scipy.stats import ttest_ind


def main():

    experiment_dir = FLAGS_experiment_dir
    num_folds = FLAGS_num_folds
    open_response_out = FLAGS_open_response_out
    metrics_to_graph = FLAGS_metrics_to_graph.split(',') if FLAGS_metrics_to_graph is not None else []
    strip_repeat_workers = False if FLAGS_allow_repeat == 1 else True
    require_correct_action = True if FLAGS_require_correct_action == 1 else False
    require_all_correct_actions = True if FLAGS_require_all_correct_actions == 1 else False
    ignore_always_choose_walk = True if FLAGS_ignore_always_choose_walk == 1 else False
    require_all_correct_survey = True if FLAGS_require_all_correct_survey == 1 else False

    seen_turk_ids = {}
    aid_to_uids = {}
    for cond in ["train", "test"]:
        for fold in range(num_folds):
            ablations = ['']
            if fold == 3:
                ablations.append('_np')
            fold = str(fold)
            for abl in ablations:
                summary_csv_fn = os.path.join(experiment_dir, "fold" + fold, cond + abl, "summary.csv")
                if os.path.isfile(summary_csv_fn):
                    with open(summary_csv_fn, 'r') as f:
                        lines = f.readlines()
                        headers = lines[0].strip().split(',')
                        for lidx in range(1, len(lines)):
                            data = lines[lidx].strip().split(',')
                            turk_id = data[headers.index('worker_id')]
                            uid = int(data[headers.index('uid')], 16)
                            if turk_id not in aid_to_uids:
                                aid_to_uids[turk_id] = []
                            aid_to_uids[turk_id].append(data[headers.index('uid')])
                            if turk_id in seen_turk_ids:
                                seen_uid = seen_turk_ids[turk_id]
                                if uid < seen_uid:  # Record earlier sighting.
                                    seen_turk_ids[turk_id] = uid
                            else:
                                seen_turk_ids[turk_id] = uid

    cond_results = {}
    open_responses = {}  # keys are turk ids, values lists of paired ((cond, fold), response)
    for cond in ["train", "test"]:
        cond_results[cond] = {}

        for fold in range(num_folds):
            ablations = ['']
            if fold == 3:
                ablations.append('_np')
            fold = str(fold)
            for abl in ablations:
                print "aggregating over cond '" + cond + "' fold " + fold + abl

                raw_results = {"task_1_correct": [],
                               "task_1_f1": [],
                               "task_1_clarification": [],
                               "task_2_correct": [],
                               "task_2_f1": [],
                               "task_2_clarification": [],
                               "task_3_correct": [],
                               "task_3_f1": [],
                               "task_3_clarification": [],
                               "tasks_easy": [],
                               "understood": [],
                               "frustrated": [],
                               "object_qs": [],
                               "use_navigation": [],
                               "use_delivery": [],
                               "use_relocation": []}
                summary_csv_fn = os.path.join(experiment_dir, "fold" + fold, cond + abl, "summary.csv")
                response_csv_fn = os.path.join(experiment_dir, "fold" + fold, cond + abl, "open_response.csv")

                if os.path.isfile(summary_csv_fn):
                    with open(summary_csv_fn, 'r') as f:
                        lines = f.readlines()
                        headers = lines[0].strip().split(',')
                        for lidx in range(1, len(lines)):
                            data = lines[lidx].strip().split(',')

                            # Aggregate over the same users we used for retraining.
                            pickle_exists = data[headers.index("pickle_exists")]
                            task_1_correct_action = data[headers.index("task_1_correct_action")]
                            task_2_correct_action = data[headers.index("task_2_correct_action")]
                            task_3_correct_action = data[headers.index("task_3_correct_action")]
                            always_chose_walk = data[headers.index("always_chose_walk")]
                            task_3_correct = data[headers.index("task_3_correct")]
                            log_exists = data[headers.index("log_exists")]
                            if (pickle_exists == "1" and log_exists == "1" and
                                    (task_3_correct == "0" or task_3_correct == "1") and
                                    (not ignore_always_choose_walk or always_chose_walk == "0") and
                                    (not require_all_correct_actions or (task_1_correct_action == "1" and
                                                                         task_2_correct_action == "1" and
                                                                         task_3_correct_action == "1"))):

                                # This is the condition and fold in which we first saw the worker.
                                turk_id = data[headers.index('worker_id')]
                                uid = int(data[headers.index('uid')], 16)
                                if (not strip_repeat_workers or
                                        (turk_id in seen_turk_ids and seen_turk_ids[turk_id] == uid)):

                                    for task in range(1, 4):
                                        if (not require_correct_action or
                                                data[headers.index("task_" + str(task) + "_correct_action")] == "1"):
                                            task_correct = int(data[headers.index("task_" + str(task) + "_correct")])
                                            task_f1 = float(data[headers.index("task_" + str(task) + "_f1")])
                                            raw_results["task_" + str(task) + "_correct"].append(task_correct)
                                            raw_results["task_" + str(task) + "_f1"].append(task_f1)
                                            if task_correct:
                                                task_user_strs = int(data[headers.index("task_" + str(task) +
                                                                                        "_clarification")])
                                                raw_results["task_" + str(task) + "_clarification"].append(
                                                    task_user_strs)

                                    if (not require_all_correct_survey or
                                            (int(data[headers.index("task_1_correct")]) and
                                             int(data[headers.index("task_2_correct")]) and
                                             int(data[headers.index("task_2_correct")]))):
                                        for sq in ["tasks_easy", "understood", "frustrated", "object_qs",
                                                   "use_navigation", "use_delivery", "use_relocation"]:
                                            raw_results[sq].append(int(data[headers.index(sq)]))
                                else:
                                    # print "WARNING: ignoring repeat worker " + turk_id
                                    pass

                if os.path.isfile(response_csv_fn):
                    with open(response_csv_fn, 'r') as f:
                        for line in f.readlines():
                            line = line.strip()
                            if len(line) > 0:
                                try:
                                    uid, r = line.split(": ")
                                    found_aid = None
                                    for aid in aid_to_uids:
                                        if uid in aid_to_uids[aid]:
                                            found_aid = aid
                                            break
                                    if found_aid is not None:
                                        if aid not in open_responses:
                                            open_responses[aid] = {}
                                        open_responses[aid][int(uid, 16)] = (cond, fold + abl, r)
                                    else:
                                        print "WARNING: no aid found for uid " + uid + " in open response files"
                                except ValueError:  # response submitted was just blank space
                                    pass

                pr = {}
                for r in raw_results:
                    n = len(raw_results[r])
                    if n > 0:
                        mu = np.mean(raw_results[r])
                        var = np.var(raw_results[r])
                        s = np.sqrt(var)
                    else:
                        mu = s = None
                    pr[r] = {"n": n, "mu": mu, "s": s, "d": raw_results[r]}
                cond_results[cond][fold + abl] = pr

        # Print results over condition.
        print "=========="
        print "condition '" + cond + "' results:"
        for r in cond_results[cond]["0"].keys():
            print "----------"
            print "\tfold\t" + r + "\t(STDDEV)\t(N)\t(SIG)"  # \t(p)"
            for fold in range(num_folds):
                ablations = ['']
                if fold == 3:
                    ablations.append('_np')
                fold = str(fold)
                for abl in ablations:
                    if cond_results[cond][fold + abl][r]["n"] > 0:

                        # Perform t-test against fold 0.
                        sig = ''
                        if fold > 0:
                            t, p = ttest_ind(cond_results[cond]["0"][r]["d"],
                                             cond_results[cond][fold + abl][r]["d"],
                                             equal_var=False)
                            if p < 0.05:
                                sig = '*'
                            elif p < 0.1:
                                sig = '+'
                            # sig += "\t" + str(p)

                        print ("\t" + fold + abl + "\t" + str(cond_results[cond][fold + abl][r]["mu"]) +
                               "\t+/-" + str(cond_results[cond][fold + abl][r]["s"]) + "\t" +
                               str(cond_results[cond][fold + abl][r]["n"]) + "\t" + sig)

    # Write open response outfile
    print "writing open response collation..."
    open_response_count = {aid: len(open_responses[aid]) for aid in open_responses.keys()}
    with open(open_response_out, 'w') as f:
        for aid, _ in sorted(open_response_count.iteritems(), key=lambda (_k, _v): (_v, _k), reverse=True):
            f.write(aid + "\n")
            for uid16, __ in sorted(open_responses[aid].iteritems()):
                cond, fold, r = open_responses[aid][uid16]
                f.write("(" + cond + ", " + fold + ")\t" + r + "\n")
            f.write("\n")
    print "... done"

    # Create and show plot for specified metric(s).
    for metric in metrics_to_graph:
        mus = []
        for cond in ["train", "test", "test_np"]:
            cond_mus = []
            for fold in range(num_folds):
                if cond == "test_np":
                    if fold == 3:
                        cond_mus.append(cond_results["test"]["3_np"][metric]["mu"])
                    else:
                        cond_mus.append(0)
                elif cond in cond_results:
                    if str(fold) in cond_results[cond]:
                        cond_mus.append(cond_results[cond][str(fold)][metric]["mu"])
                    else:
                        cond_mus.append(0)
                else:
                    cond_mus.append(0)
            cond_mus = [cond_mus[idx] if cond_mus[idx] is not None else 0
                        for idx in range(len(cond_mus))]
            mus.append(cond_mus)

        x = np.arange(4)
        h = ["Train", "Test", "Test Ablation"]
        print mus  # DEBUG
        plt.bar(x, mus[0], color='b', width=0.25)
        plt.bar(x + 0.25, mus[1], color='g', width=0.25)
        plt.bar(x + 0.5, mus[2], color='r', width=0.25)

        plt.show()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment_dir', type=str, required=True,
                        help="directory to crawl to find fold directories")
    parser.add_argument('--num_folds', type=int, required=True,
                        help="how many folds to iterate over")
    parser.add_argument('--open_response_out', type=str, required=True,
                        help="where to dump the collated open responses")
    parser.add_argument('--metrics_to_graph', type=str, required=False,
                        help="which metrics to produce plots for")
    parser.add_argument('--allow_repeat', type=int, required=False, default=1,
                        help="whether to count repeat users")
    parser.add_argument('--require_correct_action', type=int, required=False, default=0,
                        help="whether to count correctness/f1 only when users selected correct action")
    parser.add_argument('--require_all_correct_actions', type=int, required=False, default=0,
                        help=("whether to count correctness/f1 only when users selected all " +
                              "correct actions (affects survey)"))
    parser.add_argument('--ignore_always_choose_walk', type=int, required=False, default=0,
                        help="remove users who always chose the 'walk' action (affects survey)")
    parser.add_argument('--require_all_correct_survey', type=int, required=False, default=0,
                        help="only consider survey responses from users who get all tasks correct")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
