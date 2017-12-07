#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('/u/jesse/phm/tsp/')  # necessary to import CKYParser from above directory

import argparse
import os
import pickle
import time


def main():

    # Hyperparams
    time_limit = 60 * 10  # time in seconds allowed per epoch
    poll_increment = 10  # poll for finished jobs every 10 seconds

    # Load parameters from command line.
    target_dir = FLAGS_target_dir
    script_dir = FLAGS_script_dir
    agent_infile = FLAGS_agent_infile
    parse_reranker_beam = FLAGS_parse_reranker_beam
    interpolation_reranker_beam = FLAGS_interpolation_reranker_beam
    pairs_infile = FLAGS_pairs_infile
    outfile = FLAGS_outfile

    # Load agent.
    with open(agent_infile, 'rb') as f:
        a = pickle.load(f)

    # Launch jobs.
    with open(pairs_infile, 'rb') as f:
        d = pickle.load(f)
    jobs_remaining = []
    condorify_fn = os.path.join(script_dir, "condorify_gpu_email")
    script_fn = os.path.join(script_dir, "_condor_get_ground_pair.py")
    for idx in range(len(d)):
        out_fn = os.path.join(target_dir, "temp.gpair." + str(idx) + ".pickle")
        log_fn = os.path.join(target_dir, "temp.gpair." + str(idx) + ".log")
        cmd = (condorify_fn + " " +
               "python " + script_fn +
               " --agent_infile " + agent_infile +
               " --parse_reranker_beam " + str(parse_reranker_beam) +
               " --interpolation_reranker_beam " + str(interpolation_reranker_beam) +
               " --pairs_infile " + pairs_infile +
               " --pair_idx " + str(idx) +
               " --outfile " + out_fn +
               " " + log_fn)
        os.system(cmd)
        jobs_remaining.append(idx)

    # Collect jobs.
    t = []
    time_remaining = time_limit
    while len(jobs_remaining) > 0 and time_remaining > 0:
        time.sleep(poll_increment)
        time_remaining -= poll_increment

        newly_completed = []
        for idx in jobs_remaining:
            fn = os.path.join(target_dir, "temp.gpair." + str(idx) + ".pickle")
            log_fn = os.path.join(target_dir, "temp.gpair." + str(idx) + ".log")
            err_fn = ("err." + log_fn).replace("/", "-")
            try:
                with open(fn, 'rb') as f:
                    pair = pickle.load(f)
                    if pair is not None:
                        t.append(pair)
                        print ("_condor_get_utt_sem_pairs: got ground pair idx " + str(idx) + " for '" +
                               str(d[idx][0]) + "', " + a.parser.print_parse(d[idx][1]))
                        print ("_condor_get_utt_sem_pairs: ... " + pair[1])
                    else:
                        print ("_condor_get_utt_sem_pairs: got no ground pair for '" +
                               str(d[idx][0]) + "', " + a.parser.print_parse(d[idx][1]))

                    newly_completed.append(idx)

                os.system("rm " + fn)  # remove output file
                os.system("rm " + log_fn)  # remove log file
                os.system("rm " + err_fn)  # remove err file

            # Output pickle hasn't been written yet.
            except (IOError, ValueError):

                # Check for a non-empty error log, suggesting the job has crashed.
                try:
                    with open(err_fn) as f:
                        err_text = f.read()
                        if len(err_text.strip()) > 0:

                            # Error, so move on and save log.
                            print ("_condor_get_utt_sem_pairs: discovered failed job for pair idx " +
                                   str(idx) + ":\n'" + err_text + "'")
                            os.system("mv " + err_fn + " " + err_fn + ".autosave")  # preserve the error log on disk
                            newly_completed.append(idx)
                            os.system("rm " + log_fn)  # remove log

                except IOError:
                    pass

        now_remaining = [idx for idx in jobs_remaining if idx not in newly_completed]
        if len(newly_completed) > 0:
            print ("_condor_get_utt_sem_pairs: completed " + str(len(newly_completed)) +
                   " more jobs (" + str(len(d) - len(now_remaining)) + "/" + str(len(d)) + ") " +
                   "with " + str(len(t)) + " actual pairs so far")
        jobs_remaining = now_remaining[:]
    print ("_condor_get_utt_sem_pairs: finished " + str(len(d) - len(jobs_remaining)) + " of " +
           str(len(d)) + " jobs; abandoned " + str(len(jobs_remaining)) + " due to time limit; got " +
           str(len(t)) + " actual pairs")

    # Output results.
    with open(outfile, 'wb') as f:
        pickle.dump(t, f)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target_dir', type=str, required=True,
                        help="the directory to write new files")
    parser.add_argument('--script_dir', type=str, required=True,
                        help="the directory where condorify script lives")
    parser.add_argument('--agent_infile', type=str, required=True,
                        help="the agent pickle")
    parser.add_argument('--parse_reranker_beam', type=int, required=True,
                        help="how many parses to re-rank internally before returning")
    parser.add_argument('--interpolation_reranker_beam', type=int, required=True,
                        help="how many parse+grounding scores to beam down before reranking")
    parser.add_argument('--pairs_infile', type=str, required=True,
                        help="the pairs pickle")
    parser.add_argument('--outfile', type=str, required=True,
                        help="where to dump the pairs and epoch data")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
