#!/usr/bin/env python
__author__ = 'jesse'

import argparse
import pickle
import os


def main():

    summary_csv_fn = FLAGS_summary_csv
    log_dir = FLAGS_log_dir
    user_data_dir = FLAGS_user_data_dir
    outfile = FLAGS_outfile

    agg_all_utterances = []
    agg_all_parser_timeouts = 0
    agg_all_grounder_timeouts = 0
    agg_role_utterances_role_chosen_pairs = []
    agg_perceptual_labels = []
    agg_perceptual_synonymy = []
    num_users = 0
    num_correct_tasks = 0
    with open(summary_csv_fn, 'r') as f:
        lines = f.readlines()
        headers = lines[0].strip().split(',')
        for lidx in range(1, len(lines)):
            data = lines[lidx].strip().split(',')

            # Aggregate users if they completed task 3 (correctly or not).
            # We could conceivably draw data from users who did not complete all tasks as well.
            uid = data[headers.index("uid")]
            pickle_exists = data[headers.index("pickle_exists")]
            task_3_correct = data[headers.index("task_3_correct")]
            log_exists = data[headers.index("log_exists")]
            if (pickle_exists == "1" and log_exists == "1"):

                # Load user utterances from logfile.
                log_fn = os.path.join(log_dir, uid + ".log")
                with open(log_fn, 'r') as log_f:
                    for l in log_f.readlines():
                        ps = l.strip().split(': ')
                        if len(ps) > 1:
                            msg_type = ps[0]
                            msg = ': '.join(ps[1:])
                            if msg_type == "get_from_user (processed)":
                                agg_all_utterances.append(msg)

                # Load user data from log pickle.
                pickle_fn = os.path.join(user_data_dir, uid + ".pickle")
                with open(pickle_fn, 'rb') as pickle_f:
                    actions_confirmed, utterances_by_role, new_perceptual_labels, perceptual_pred_synonymy, \
                        parser_timeouts_per_dialog, grounder_timeouts_per_dialog = pickle.load(pickle_f)

                    tasks_correct = [True if data[headers.index("task_" + str(task) + "_correct")] == "1" else False
                                     for task in range(1, 4)]
                    for task in range(1, 4):
                        idx = task - 1
                        # If task was correct, note this user's data for inclusion in aggregated pickle.
                        if tasks_correct[idx]:
                            pair = (actions_confirmed[idx], utterances_by_role[idx])
                            if pair not in agg_role_utterances_role_chosen_pairs:
                                agg_role_utterances_role_chosen_pairs.append((actions_confirmed[idx],
                                                                              utterances_by_role[idx]))
                            num_correct_tasks += 1

                    # Regardless of correctness, record perceptual labels gathered from this user.
                    agg_perceptual_labels.extend(new_perceptual_labels)
                    agg_perceptual_synonymy.extend(perceptual_pred_synonymy)

                    # Count the number of parsing and grounding timeouts from this user's dialogs.
                    for tidx in range(len(parser_timeouts_per_dialog)):
                        agg_all_parser_timeouts += parser_timeouts_per_dialog[tidx]
                        agg_all_grounder_timeouts += grounder_timeouts_per_dialog[tidx]

                    num_users += 1

    if num_users == 0:
        print("ERROR: found no users")
        return 1

    # Report.
    print ("main: aggregated data from " + str(num_users) + " users and " + str(num_correct_tasks) + " correct " +
           "tasks for an average correct tasks per user of " + str(num_correct_tasks / float(num_users)))
    print ("main: got a total of " + str(len(agg_all_utterances)) + " string utterances over all those users, with " +
           str(agg_all_parser_timeouts) + " of those leading to parser timeouts and " +
           str(agg_all_grounder_timeouts) + " leading to grounder timeouts")
    print ("main: this resulted in " + str(len(agg_role_utterances_role_chosen_pairs)) +
           " pairs of confirmed actions with dialog utterances per role")
    print ("main: for perception, this gives " + str(len(agg_perceptual_labels)) + " new perceptual labels over " +
           str(len(set([pred for pred, _, _ in agg_perceptual_labels]))) + " predicates")
    print ("main: for synonymy, this gives " + str(len(agg_perceptual_synonymy)) + " new synonymy relationship labels")

    # Record.
    with open(outfile, 'wb') as f:
        d = [agg_all_utterances, agg_role_utterances_role_chosen_pairs,
             agg_perceptual_labels, agg_perceptual_synonymy,
             agg_all_parser_timeouts, agg_all_grounder_timeouts]
        pickle.dump(d, f)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--summary_csv', type=str, required=True,
                        help="the summary csv generated by approve_mturk.py to aggregate users over")
    parser.add_argument('--log_dir', type=str, required=True,
                        help="where logfiles were stored during experiment")
    parser.add_argument('--user_data_dir', type=str, required=True,
                        help="where user data was stored during experiment")
    parser.add_argument('--outfile', type=str, required=True,
                        help="the outfile pickle to store the aggregated data")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
