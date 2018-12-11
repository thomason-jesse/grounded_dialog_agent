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
    include_correct_role_pairs = FLAGS_include_correct_role_pairs
    drop_f1_zero_perc_syn_data = FLAGS_drop_f1_zero_perc_syn_data
    remove_contrasting_pairs = FLAGS_remove_contrasting_pairs

    agg_all_utterances = []
    agg_all_parser_timeouts = 0
    agg_all_grounder_timeouts = 0
    agg_role_utterances_role_chosen_pairs = []
    agg_action_role_utterance_pairs = {}
    agg_perceptual_labels = []
    agg_perceptual_synonymy = []
    num_users = [0, 0, 0]
    num_correct_tasks = [0, 0, 0]
    f1_zero_users = 0
    with open(summary_csv_fn, 'r') as f:
        lines = f.readlines()
        headers = lines[0].strip().split(',')
        for lidx in range(1, len(lines)):
            data = lines[lidx].strip().split(',')

            # Aggregate users if they completed the task (correctly or not)
            # We could conceivably draw data from users who did not complete all tasks as well.
            uid = data[headers.index("uid")]
            pickle_exists = data[headers.index("pickle_exists")]
            log_exists = data[headers.index("log_exists")]
            if pickle_exists == "1" and log_exists == "1":

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
                    tasks_taken = [False if data[headers.index("task_" + str(task) + "_correct")] == "-2" else True
                                   for task in range(1, 4)]
                    f1 = None
                    for task in range(1, 4):
                        idx = task - 1
                        # If task was correct, note this user's data for inclusion in aggregated pickle.
                        if tasks_correct[idx] or include_correct_role_pairs == 1:
                            pair = (actions_confirmed[0], utterances_by_role[0])
                            if pair not in agg_role_utterances_role_chosen_pairs:
                                agg_role_utterances_role_chosen_pairs.append((actions_confirmed[0],
                                                                              utterances_by_role[0]))
                            for role in actions_confirmed[0]:
                                if role not in agg_action_role_utterance_pairs:
                                    agg_action_role_utterance_pairs[role] = {}
                                if (actions_confirmed[0][role] is not None and
                                        data[headers.index("task_" + str(task) + "_correct_" + role)] == "1"):
                                    acr = actions_confirmed[0][role]
                                    if acr not in agg_action_role_utterance_pairs[role]:
                                        agg_action_role_utterance_pairs[role][acr] = []
                                    agg_action_role_utterance_pairs[role][acr].extend(utterances_by_role[0][role])
                            # build full action command for original phrase and rephrasings
                            # even if including partials, must be fully correct to include 'all' pairs
                            if 'all' in utterances_by_role[0] and tasks_correct[idx]:
                                if 'all' not in agg_action_role_utterance_pairs:
                                    agg_action_role_utterance_pairs['all'] = {}
                                if actions_confirmed[0]['action'] == 'walk':
                                    acr = "walk" + "(" + actions_confirmed[0]['goal'] + ")"
                                elif actions_confirmed[0]['action'] == 'bring':
                                    acr = ("bring" + "(" + actions_confirmed[0]['patient'] + "," +
                                           actions_confirmed[0]['recipient'] + ")")
                                else:
                                    acr = ("move" + "(" + actions_confirmed[0]['patient'] + "," +
                                           actions_confirmed[0]['source'] + "," + actions_confirmed[0]['goal'] + ")")
                                if acr not in agg_action_role_utterance_pairs['all']:
                                    agg_action_role_utterance_pairs['all'][acr] = []
                                agg_action_role_utterance_pairs['all'][acr].extend(utterances_by_role[0]['all'])

                            num_correct_tasks[idx] += 1
                        if tasks_taken[idx]:
                            num_users[idx] += 1
                            f1 = float(data[headers.index("task_" + str(task) + "_f1")])

                    # If user got at least one semantic role correct, tenuously trust their perceptual labels and
                    # synonymy decisions.
                    if f1 > 0 or not drop_f1_zero_perc_syn_data:
                        # Record perceptual labels gathered from this user.
                        agg_perceptual_labels.extend(new_perceptual_labels)
                        agg_perceptual_synonymy.extend(perceptual_pred_synonymy)
                    if f1 == 0:
                        f1_zero_users += 1

                    # Count the number of parsing and grounding timeouts from this user's dialogs.
                    for tidx in range(len(parser_timeouts_per_dialog)):
                        agg_all_parser_timeouts += parser_timeouts_per_dialog[tidx]
                        agg_all_grounder_timeouts += grounder_timeouts_per_dialog[tidx]

    if num_users == 0:
        print("ERROR: found no users")
        return 1

    # Make as pass through agg_action_role_utterance_pairs role grounding<->utterance pairs for contrastive examples
    # where for a role, two groundings A and B have been paired to the same utterance U. These noisy pairs can be
    # filtered out before training to reduce confusion in the parser coming from users underspecifying groundings.
    if remove_contrasting_pairs:
        utt_to_r_g = {}
        for r in agg_action_role_utterance_pairs:
            for g in agg_action_role_utterance_pairs[r]:
                for u in agg_action_role_utterance_pairs[r][g]:
                    if u not in utt_to_r_g:
                        utt_to_r_g[u] = []
                    utt_to_r_g[u].append((r, g))
        utt_to_unique = {u: utt_to_r_g[u][0] for u in utt_to_r_g if len(set(utt_to_r_g[u])) == 1}
        new_pairs = {r: {g: [u for u in utt_to_unique
                             if u in utt_to_unique and utt_to_unique[u] == (r, g)]
                         for g in agg_action_role_utterance_pairs[r]}
                     for r in agg_action_role_utterance_pairs}
        agg_action_role_utterance_pairs = new_pairs

    # DEBUG
    total_pairs = 0
    for r in agg_action_role_utterance_pairs:
        print(r + " (" + str(sum([len(agg_action_role_utterance_pairs[r][t])
                                  for t in agg_action_role_utterance_pairs[r]])) + ")")
        for t in agg_action_role_utterance_pairs[r]:
            print('\t' + t + " (" + str(len(agg_action_role_utterance_pairs[r][t])) + ")")
            for u in agg_action_role_utterance_pairs[r][t]:
                print('\t\t' + u)
            total_pairs += len(agg_action_role_utterance_pairs[r][t])

    # Report.
    print ("main: aggregated data from " + str(num_users) + " users and " + str(num_correct_tasks) + " correct " +
           "tasks for an average correct tasks per user of " +
           ', '.join(['%.2f' % (num_correct_tasks[idx] / float(num_users[idx]) if num_users[idx] > 0 else 0) for idx in range(3)]))
    print ("main: got a total of " + str(len(agg_all_utterances)) + " string utterances over all those users, with " +
           str(agg_all_parser_timeouts) + " of those leading to parser timeouts and " +
           str(agg_all_grounder_timeouts) + " leading to grounder timeouts")
    print ("main: this resulted in " + str(total_pairs) +
           " total grounding<->utterance pairs across all roles (including 'all')")
    print ("main: for perception, this gives " + str(len(agg_perceptual_labels)) + " new perceptual labels over " +
           str(len(set([pred for pred, _, _ in agg_perceptual_labels]))) + " predicates")
    print ("main: for synonymy, this gives " + str(len(agg_perceptual_synonymy)) + " new synonymy relationship labels")
    psstr = "dropped" if drop_f1_zero_perc_syn_data else "kept"
    print ("main: for perception and synonymy, " + psstr + " data from " + str(f1_zero_users) + "/" +
           str(sum(num_users)) + " (%.2f" % (f1_zero_users / sum(num_users)) + ") users with zero f1")

    # Record.
    with open(outfile, 'wb') as f:
        d = [agg_all_utterances, agg_action_role_utterance_pairs,
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
    parser.add_argument('--include_correct_role_pairs', type=int, required=True,
                        help="whether to get grounding<->utterance pairs from users with partially correct " +
                             "confirmations")
    parser.add_argument('--drop_f1_zero_perc_syn_data', type=int, required=True,
                        help="whether to drop perceptual labels and synonymy data from zero-f1-scoring users")
    parser.add_argument('--remove_contrasting_pairs', type=int, required=True,
                        help="whether to remove contrasting A<->U B<->U ground<->utterance pairs")
    parser.add_argument('--outfile', type=str, required=True,
                        help="the outfile pickle to store the aggregated data")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
