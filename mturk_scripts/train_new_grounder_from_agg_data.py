#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../../tsp')  # necessary to use Ontology, Lexicon, CKYParser, etc.
sys.path.append('../')  # necessary to import Agent, IO from above directory

import argparse
import pickle
import Agent
import IO


def main():

    # Load parameters from command line.
    grounder_fn = FLAGS_grounder_fn
    agg_fn = FLAGS_agg_fn

    # Load the aggregate information from file
    print "main: loading aggregate conversation file..."
    with open(agg_fn, 'rb') as f:
        agg_role_utterances_role_chosen_pairs, agg_perceptual_labels, agg_perceptual_synonymy = pickle.load(f)
    print "... done"

    # Load a grounder from file
    print "main: loading grounder from file..."
    with open(grounder_fn, 'rb') as f:
        g = pickle.load(f)
    print "main: ... done"

    # Grab a reference to the parser from the loaded grounder.
    p = g.parser

    # Instantiate an input/output
    print "main: instantiating basic IO..."
    io = IO.KeyboardIO()
    print "main: ... done"

    # Instantiate an Agent.
    print "main: instantiating Agent..."
    a = Agent.Agent(p, g, io, None)
    print "main: ... done"

    # Analyze synonymy votes and decide which pairs to treat as synonymous.
    synonymy_votes = {}  # maps from tuples of preds to the sum of votes for and against their being synonymous
    for predi, predj, v in agg_perceptual_synonymy:
        if (predi, predj) in synonymy_votes:
            key = (predi, predj)
        elif (predj, predi) in synonymy_votes:
            key = (predj, predi)
        else:
            key = (predi, predj)
            synonymy_votes[key] = 0
        synonymy_votes[key] += 1 if v else -1
    print synonymy_votes  # DEBUG
    synonymy_candidates = [key for key in synonymy_votes.keys() if synonymy_votes[key] > 0]
    print synonymy_candidates  # DEBUG

    # Decide based on synonymy and pred labels which lexicon entries to add (similar to procedure in Agent.py,
    # but based on voting instead of single-user feedback.)
    # TODO: in general, probably break a lot of the functionality for this out of Agent.py by making the
    # TODO: relevant functions there more modular, especially for things like adj/n detection and
    # TODO: adding things to the lexicon based on synonymy.
    preds_w_pos_labels = list(set([pred for pred, _, label in agg_perceptual_labels
                          if label]))
    print preds_w_pos_labels  # DEBUG
    # We only add predicates to the system if they ever got a positive example, because this helps filter
    # users saying words are perceptual without really meaning it, then having to backtrack and say "None"
    # when the system asks them to show an example of something they would call, for example, "d".
    utterances_with_pred = {}
    for pred in preds_w_pos_labels:
        utterances_with_pred[pred] = []
        for _, utterances_by_role in agg_role_utterances_role_chosen_pairs:
            for r in utterances_by_role.keys():
                for u in utterances_by_role[r]:
                    if pred in u:
                        utterances_with_pred[pred].append(u)

    pred_is_adj = {}
    for pred in preds_w_pos_labels:

        # TODO: decide whether each predicate is a noun or adjective by iterating over all the predicates,
        # TODO: greedily assigning each as either adj/noun until all assignments are complete.

        pass

    # Retrain perceptual classifiers from aggregated labels.
    # TODO

    # Induce pairs from agg data.
    print "main: creating induced pairs from aggregated conversations..."
    for action_confirmed, user_utterances_by_role in agg_role_utterances_role_chosen_pairs:
        new_i_pairs = a.induce_utterance_grounding_pairs_from_conversation(user_utterances_by_role,
                                                                           action_confirmed)
        a.induced_utterance_grounding_pairs.extend(new_i_pairs)
    print "main: ... done; induced " + str(len(a.induced_utterance_grounding_pairs)) + " pairs"

    # Retrain parser from induced pairs.
    print "main: re-training parser on pairs induced from aggregated conversations..."
    a.train_parser_from_induced_pairs(10, 1, 3, verbose=2)
    print "main: ... done"

    # TODO: new grounder needs to live in a new place and point to a new perceptual directory where
    # TODO: it can write out base classifiers that won't interfere with less trained versions.


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--grounder_fn', type=str, required=True,
                        help="a grounder pickle to load as a training base")
    parser.add_argument('--agg_fn', type=str, required=True,
                        help="the aggregated data for the users to use as retraining material")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
