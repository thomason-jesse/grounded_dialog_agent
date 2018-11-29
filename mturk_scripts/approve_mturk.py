#!/usr/bin/env python
__author__ = 'jesse'

import argparse
import csv
import hashlib
import os


def main():

    csv_fns = FLAGS_csvs.split(',')
    add_salts = FLAGS_add_salts.split(',')
    user_data_dir = FLAGS_user_data_dir
    log_dir = FLAGS_log_dir
    outfile = FLAGS_outfile
    open_response_outfile = FLAGS_open_response_outfile
    show_bonus = True if FLAGS_show_bonus == 1 else False

    user_data_to_write = []
    user_open_responses_to_write = []
    mturk_ids_to_bonus = []
    mturk_ids_not_to_bonus = []
    for csv_idx in range(len(csv_fns)):
        csv_fn = csv_fns[csv_idx]
        add_salt = add_salts[csv_idx]
        with open(csv_fn, 'r') as f:

            inreader = csv.reader(f)
            first = True
            valid = 0
            total = 0
            ids_seen = []
            survey_header = id_header = None
            for row in inreader:

                if first:
                    survey_header = row.index("Answer.surveycode")
                    id_header = row.index("WorkerId")
                    first = False

                else:
                    code = row[survey_header]
                    if '_' in code:
                        code_parts = code.split('_')
                        if len(code_parts) > 3:
                            print (row[id_header] + " survey code doesn't match form '" + code + "'")
                            total += 1
                            continue
                        gen_id, rot_mid, id_hash = code.split('_')
                        mid = rot_mid[-3:] + rot_mid[:-3]
                        stripped_mid = mid.strip()
                        true_hash = hashlib.sha1("phm_salted_hash" + gen_id + mid +
                                                 "rwhpidcwha_" + add_salt).hexdigest()[:13]
                        if id_hash != true_hash:
                            print (row[id_header] + " gen id " + gen_id +
                                   " gave hash " + id_hash + " != " + true_hash)
                        elif id_hash in ids_seen:
                            print(row[id_header] + " gen id " + gen_id + " already seen")
                        elif stripped_mid != row[id_header]:
                            print(row[id_header] + " provided non-matching worker id '" + mid + "'")
                        else:
                            valid += 1

                            # Process this worker to create output line in out CSV
                            # and to determine bonuses.
                            user_data = {"worker_id": row[id_header],
                                         "uid": gen_id,
                                         "task_1_correct": "-2",
                                         "task_2_correct": "-2",
                                         "task_3_correct": "-2",
                                         "task_1_correct_action": "-2",
                                         "task_2_correct_action": "-2",
                                         "task_3_correct_action": "-2",
                                         "task_1_f1": "-1",
                                         "task_2_f1": "-1",
                                         "task_3_f1": "-1",
                                         "pickle_exists": '0',
                                         "tasks_easy": "-1",
                                         "understood": "-1",
                                         "frustrated": "-1",
                                         "object_qs": "-1",
                                         "use_navigation": "-1",
                                         "use_delivery": "-1",
                                         "use_relocation": "-1",
                                         "log_exists": "0",
                                         "task_1_str_from_user": "0",
                                         "task_1_enum_from_user": "0",
                                         "task_1_oidx_from_user": "0",
                                         "task_1_clarification": "0",
                                         "task_1_perception_q": "0",
                                         "task_1_synonym": "0",
                                         "task_1_perception_yn": "0",
                                         "task_1_perception_ex": "0",
                                         "task_2_str_from_user": "0",
                                         "task_2_enum_from_user": "0",
                                         "task_2_oidx_from_user": "0",
                                         "task_2_clarification": "0",
                                         "task_2_perception_q": "0",
                                         "task_2_synonym": "0",
                                         "task_2_perception_yn": "0",
                                         "task_2_perception_ex": "0",
                                         "task_3_str_from_user": "0",
                                         "task_3_enum_from_user": "0",
                                         "task_3_oidx_from_user": "0",
                                         "task_3_clarification": "0",
                                         "task_3_perception_q": "0",
                                         "task_3_synonym": "0",
                                         "task_3_perception_yn": "0",
                                         "task_3_perception_ex": "0",
                                         "error_found_in_logfile": "0",
                                         "warning_found_in_logfile": "0",
                                         "incomplete_logfile": "1"}
                            user_open_response = None

                            # First, mark the tasks the user completed correctly.
                            # task_N_correct vars will remain -2 if task was never drawn.
                            # task_N_correct vars will become -1 if task was drawn but not completed.
                            bonuses = 0
                            completed_task = None
                            for task in range(1, 4):
                                drawn_fn = os.path.join(user_data_dir, gen_id + "." + str(task) + ".drawn.txt")
                                if os.path.isfile(drawn_fn):
                                    user_data["task_" + str(task) + "_correct"] = '-1'
                                    user_data["task_" + str(task) + "_correct_action"] = '-1'
                                    with open(drawn_fn, 'r') as drawn_f:
                                        drawn_roles = {}
                                        for rv_str in drawn_f.read().strip().split(';'):
                                            rv = rv_str.split(':')
                                            drawn_roles[rv[0]] = rv[1]
                                    chosen_fn = os.path.join(user_data_dir, gen_id + "." + str(task) + ".chosen.txt")
                                    if os.path.isfile(chosen_fn):
                                        with open(chosen_fn, 'r') as chosen_f:
                                            chosen_roles = {}
                                            chosen_str = chosen_f.read().strip()
                                            if len(chosen_str) > 0:
                                                completed_task = task
                                                for rv_str in chosen_str.split(';'):
                                                    rv = rv_str.split(':')
                                                    if rv[1] != 'None':
                                                        chosen_roles[rv[0]] = rv[1]
                                                task_correct = True
                                                for r in drawn_roles:
                                                    if r not in chosen_roles or chosen_roles[r] != drawn_roles[r]:
                                                        task_correct = False
                                                user_data["task_" + str(task) + "_correct"] = '1' if task_correct else '0'
                                                user_data["task_" + str(task) + "_correct_action"] = '1' if \
                                                    chosen_roles['action'] == drawn_roles['action'] else '0'
                                                if task_correct:
                                                    bonuses += 1
                                                overlap_n = 0
                                                for r in drawn_roles:
                                                    if r in chosen_roles and chosen_roles[r] == drawn_roles[r]:
                                                        overlap_n += 1
                                                prec = float(overlap_n) / len(chosen_roles)
                                                rec = float(overlap_n) / len(drawn_roles)
                                                f1 = 2 * (prec * rec) / (prec + rec) if prec + rec > 0 else 0
                                                user_data["task_" + str(task) + "_f1"] = str(f1)

                            # Check whether output pickle exists (user finished dialog agent script in main.py)
                            pickle_fn = os.path.join(user_data_dir, gen_id + ".pickle")
                            if os.path.isfile(pickle_fn):
                                user_data["pickle_exists"] = '1'

                            # Open and digest the user survey into the output CSV.
                            survey_fn = os.path.join(user_data_dir, gen_id + ".survey.txt")
                            if os.path.isfile(survey_fn):
                                with open(survey_fn, 'r') as survey_f:
                                    ls = survey_f.readlines()
                                    for idx in range(7):
                                        q, v = ls[idx].strip().split(',')
                                        user_data[q] = v
                                    if len(ls) > 7:
                                        user_open_response = ls[7].strip()

                            # Open logfile and count turns; check for errors.
                            log_fn = os.path.join(log_dir, gen_id + ".log")
                            if os.path.isfile(log_fn):
                                user_data["log_exists"] = "1"
                                with open(log_fn, 'r') as log_f:
                                    contents = log_f.read().strip()

                                    lines = contents.split('\n')
                                    str_from_user_count = None
                                    enum_from_user_count = None
                                    oidx_from_user_count = None
                                    perception_q_count = None
                                    synonym_count = None
                                    perception_yn_count = None
                                    perception_ex_count = None
                                    for l in lines:
                                        ps = l.split(': ')
                                        if len(ps) > 1:
                                            msg_type = ps[0]
                                            msg = ': '.join(ps[1:])

                                            # First line of log.
                                            if (msg_type == "say_to_user_with_referents" and
                                                    msg == "What should I do? {}"):

                                                str_from_user_count = 0
                                                enum_from_user_count = 0
                                                oidx_from_user_count = 0
                                                perception_q_count = 0
                                                synonym_count = 0
                                                perception_yn_count = 0
                                                perception_ex_count = 0

                                            # Got string from user.
                                            elif msg_type == "get_from_user (processed)":
                                                str_from_user_count += 1

                                            elif msg_type == "get_from_user_enum":
                                                enum_from_user_count += 1

                                            # Got oidx from user.
                                            elif msg_type == "get_oidx_from_user":
                                                oidx_from_user_count += 1

                                            # Record question types asked by system.
                                            elif msg_type == "say_to_user_with_referents":

                                                # Asked user for an example object.
                                                if "Among these nearby objects," in msg:
                                                    perception_ex_count += 1

                                                # Asked user whether pred applied to object.
                                                elif "Would you use the word" in msg:
                                                    perception_yn_count += 1

                                                # Asked the user a perception word question.
                                                elif "I haven't heard the word" in msg:
                                                    perception_q_count += 1

                                                # Asked the user a synonym question.
                                                elif "mean the same thing as" in msg:
                                                    synonym_count += 1

                                    # Finished reading log and found a completed task.
                                    if str_from_user_count is not None and completed_task is not None:
                                        user_data["task_" + str(completed_task) + "_str_from_user"] = \
                                            str(str_from_user_count)
                                        user_data["task_" + str(completed_task) + "_enum_from_user"] = \
                                            str(enum_from_user_count)
                                        user_data["task_" + str(completed_task) + "_oidx_from_user"] = \
                                            str(oidx_from_user_count)

                                        clarification_qs = ((str_from_user_count + enum_from_user_count) -
                                                            perception_yn_count - perception_q_count -
                                                            synonym_count)
                                        user_data["task_" + str(completed_task) + "_clarification"] = \
                                            str(clarification_qs)
                                        user_data["task_" + str(completed_task) + "_perception_q"] = \
                                            str(perception_q_count)
                                        user_data["task_" + str(completed_task) + "_synonym"] = \
                                            str(synonym_count)
                                        user_data["task_" + str(completed_task) + "_perception_yn"] = \
                                            str(perception_yn_count)
                                        user_data["task_" + str(completed_task) + "_perception_ex"] = \
                                            str(perception_ex_count)

                                    # Check for errors.
                                    if "Error" in contents:
                                        user_data["error_found_in_logfile"] = "1"
                                    if "WARNING" in contents:
                                        user_data["warning_found_in_logfile"] = "1"

                            # Store.
                            user_data_to_write.append(user_data)
                            if user_open_response is not None:
                                user_open_responses_to_write.append(gen_id + ": " + user_open_response)

                            # Bonuses.
                            if bonuses > 0:
                                # print(row[id_header] + " gen id " + gen_id + " bonuses: " + str(bonuses))
                                mturk_ids_to_bonus.append(mid)
                            else:
                                mturk_ids_not_to_bonus.append(mid)

                            # Alert error.
                            if user_data["error_found_in_logfile"] == "1":
                                print ("WARNING: " + row[id_header] + " gen id " + gen_id +
                                       " logfile may contain runtime error report")

                            # Alert warning.
                            if user_data["warning_found_in_logfile"] == "1":
                                print ("WARNING: " + row[id_header] + " gen id " + gen_id +
                                       " logfile may contain runtime warning report")

                    else:
                        print(row[id_header] + " gen id " + gen_id + " invalid survey code " + code)
                    total += 1
                    ids_seen.append(gen_id)
            print(str(valid) + " workers of " + str(total) + " were valid ('" + csv_fn + "')")

    # Write CSV output data.
    with open(outfile, 'w') as f:
        headers = set()
        for user_data in user_data_to_write:
            headers = headers.union(set(user_data.keys()))
        f.write(','.join(headers) + '\n')
        for user_data in user_data_to_write:
            f.write(','.join([user_data[h] for h in headers]) + '\n')

    with open(open_response_outfile, 'w') as f:
        for open_response in user_open_responses_to_write:
            f.write(open_response + '\n\n')

    # Print bonus information.
    if show_bonus:
        if len(mturk_ids_to_bonus) < len(mturk_ids_not_to_bonus):
            print("Bonus these workers, approve else:\n" + '\n'.join(mturk_ids_to_bonus))
        else:
            print("Approve (do not bonus) these workers; bonus else:\n" + '\n'.join(mturk_ids_to_bonus))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csvs', type=str, required=True,
                        help="input csvs, comma separated")
    parser.add_argument('--add_salts', type=str, required=True,
                        help="additional salt values added after key code and underscore, comma separated")
    parser.add_argument('--user_data_dir', type=str, required=True,
                        help="where user data was stored during experiment")
    parser.add_argument('--log_dir', type=str, required=True,
                        help="where logs were stored during experiment")
    parser.add_argument('--outfile', type=str, required=True,
                        help="output CSV summarizing user information currently across many files")
    parser.add_argument('--open_response_outfile', type=str, required=True,
                        help="output containing just open responses")
    parser.add_argument('--show_bonus', type=int, required=True,
                        help="whether to show bonuses")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
