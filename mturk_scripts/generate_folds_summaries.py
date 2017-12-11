#!/usr/bin/env python
__author__ = 'jesse'

import argparse
import numpy as np
import os


def main():

    experiment_dir = FLAGS_experiment_dir
    num_folds = FLAGS_num_folds
    outfile = FLAGS_outfile

    cond_results = {}
    for cond in ["train", "test"]:
        cond_results[cond] = []

        for fold in range(num_folds):

            # This stores lists of the actual data values before averaging but after selecting for retrain-able users.
            raw_results = {"task_1_correct": [],
                           "task_1_str_from_user": [],
                           "task_2_correct": [],
                           "task_2_str_from_user": [],
                           "task_3_correct": [],
                           "task_3_str_from_user": []}
            summary_csv_fn = os.path.join(experiment_dir, "fold" + str(fold), cond, "summary.csv")

            with open(summary_csv_fn, 'r') as f:
                lines = f.readlines()
                headers = lines[0].strip().split(',')
                for lidx in range(1, len(lines)):
                    data = lines[lidx].strip().split(',')

                    # Aggregate over the same users we used for retraining.
                    pickle_exists = data[headers.index("pickle_exists")]
                    task_3_correct = data[headers.index("task_3_correct")]
                    log_exists = data[headers.index("log_exists")]
                    if (pickle_exists == "1" and log_exists == "1" and
                            (task_3_correct == "0" or task_3_correct == "1")):

                        for task in range(1, 4):
                            task_correct = int(data[headers.index("task_" + str(task) + "_correct")])
                            raw_results["task_" + str(task) + "_correct"].append(task_correct)
                            if task_correct:
                                task_user_strs = int(data[headers.index("task_" + str(task) + "_str_from_user")])
                                raw_results["task_" + str(task) + "_str_from_user"].append(task_user_strs)

            pr = {}
            for r in raw_results:
                n = len(raw_results[r])
                mu = np.mean(raw_results[r])
                var = np.var(raw_results[r])
                s = np.sqrt(var)
                pr[r] = {"n": n, "mu": mu, "s": s}
            cond_results[cond].append(pr)

        # Print results over condition.
        print "=========="
        print "condition '" + cond + "' results:"
        for r in cond_results[cond][0].keys():
            print "----------"
            print "\tfold\t" + r + "\t(STDDEV)\t(N)"
            for fold in range(num_folds):
                print ("\t" + str(fold) + "\t" + str(cond_results[cond][fold][r]["mu"]) +
                       "\t+/-" + str(cond_results[cond][fold][r]["s"]) + "\t" +
                       str(cond_results[cond][fold][r]["n"]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment_dir', type=str, required=True,
                        help="directory to crawl to find fold directories")
    parser.add_argument('--num_folds', type=int, required=True,
                        help="how many folds to iterate over")
    parser.add_argument('--outfile', type=str, required=True,
                        help="the outfile to store structured averages and stddevs")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
