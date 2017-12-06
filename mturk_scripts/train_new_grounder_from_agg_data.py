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
    p.lexicon.wv = None  # if the parser has word embeddings, we don't want to use them during training

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
    print "main: synonymy votes: " + str(synonymy_votes)
    synonymy_candidates = [key for key in synonymy_votes.keys() if synonymy_votes[key] > 0]
    print "main: synonymy candidates: " + str(synonymy_candidates)

    # Decide based on synonymy and pred labels which lexicon entries to add (similar to procedure in Agent.py,
    # but based on voting instead of single-user feedback.)
    preds = list(set([pred for pred, _, _ in agg_perceptual_labels] +
                     [pred for pred, _ in synonymy_votes.keys()] +
                     [pred for _, pred in synonymy_votes.keys()]))
    print "main: preds to consider: " + str(preds)
    utterances_with_pred = {}
    for pred in preds:
        utterances_with_pred[pred] = []
        for _, utterances_by_role in agg_role_utterances_role_chosen_pairs:
            for r in utterances_by_role.keys():
                for u in utterances_by_role[r]:
                    if pred in a.parser.tokenize(u):
                        utterances_with_pred[pred].append(u)

    # Iterate over pedicates to identify likely adjectives (those left of other already-known predicates).
    # This process should repeat until no further adjectives around found (allowing chaining unseen adjs).
    # Afterwards, any predicate not flagged as an adjective is probably a noun (no percept neighbors to the right).
    pred_is_adj = {pred: False for pred in preds}
    new_adjs = True
    while new_adjs:
        print "main: checking for new adjectives..."
        new_adjs = False
        for pred in preds:
            if not pred_is_adj[pred]:
                adj_votes = [a.is_token_adjective(a.parser.tokenize(u).index(pred),
                                                  a.parser.tokenize(u))
                             for u in utterances_with_pred[pred]]
                nt = adj_votes.count(True)
                if nt >= len(adj_votes) / 2.0 and nt > 0:
                    pred_is_adj[pred] = True
                    new_adjs = True
                    # print ("main: decided '" + pred + "' was adj based on utterances: " +
                    #        "\n\t".join(utterances_with_pred[pred]))

                    # Add new adjective to lexicon.
                    syn = get_syn_from_candidates(a, pred, synonymy_candidates)
                    a.add_new_perceptual_lexical_entries(pred, True, syn)

                    print "main: added adjective '" + pred + "'"
                    if syn is not None:
                        print "main: ... with known synonym '" + a.parser.lexicon.surface_forms[syn[0]] + "'"
    print "main: adding remaining predicates as nouns..."
    for pred in preds:
        # We only add noun predicates to the system if they ever got a positive example, because this helps filter
        # users saying words are perceptual without really meaning it, then having to backtrack and say "None"
        # when the system asks them to show an example of something they would call, for example, "d".
        if not pred_is_adj[pred] and len(utterances_with_pred[pred]) > 0:
            if len([1 for _pred, _, label in agg_perceptual_labels
                    if _pred == pred and label]) > 0:
                syn = get_syn_from_candidates(a, pred, synonymy_candidates)
                a.add_new_perceptual_lexical_entries(pred, False, syn)

                print "main: added noun '" + pred + "'"
                if syn is not None:
                    print "main: ... with known synonym '" + a.parser.lexicon.surface_forms[syn[0]] + "'"
    print "main: ... done"

    # Retrain perceptual classifiers from aggregated labels.
    upidxs = []
    uoidxs = []
    ulabels = []
    for pred, oidx, label in agg_perceptual_labels:
        if pred in a.grounder.kb.pc.predicates:
            pidx = a.grounder.kb.pc.predicates.index(pred)
            upidxs.append(pidx)
            uoidxs.append(oidx)
            ulabels.append(1 if label else 0)
    print ("main: updating predicate classifiers with " + str(len(upidxs)) + " new labels across " +
           str(len(set(upidxs))) + " predicates...")
    a.grounder.kb.pc.update_classifiers([], upidxs, uoidxs, ulabels)
    print "main: ... done"

    # TODO: the following should probably be done in a loop so changes to the parser can improve possible
    # TODO: induction at the next epoch.

    # Induce pairs from agg data.
    print "main: creating induced pairs from aggregated conversations..."
    for action_confirmed, user_utterances_by_role in agg_role_utterances_role_chosen_pairs:
        new_i_pairs = a.induce_utterance_grounding_pairs_from_conversation(user_utterances_by_role,
                                                                           action_confirmed)
        # TODO: add option to parallelize this
        a.induced_utterance_grounding_pairs.extend(new_i_pairs)
    print "main: ... done; induced " + str(len(a.induced_utterance_grounding_pairs)) + " pairs"

    # Retrain parser from induced pairs.
    print "main: re-training parser on pairs induced from aggregated conversations..."
    # TODO: this should train not just on induced pairs but on parser init pairs as well
    # TODO: add option to parallelize this
    a.train_parser_from_induced_pairs(10, 1, 3, verbose=2)
    print "main: ... done"

    # TODO: new grounder needs to live in a new place and point to a new perceptual directory where
    # TODO: it can write out base classifiers that won't interfere with less trained versions.


def get_syn_from_candidates(a, pred, synonymy_candidates):
    syn = None
    for key in synonymy_candidates:
        nsfidx = None
        if key[0] == pred and key[1] in a.parser.lexicon.surface_forms:
            nsfidx = a.parser.lexicon.surface_forms.index(key[1])
        elif key[1] == pred and key[0] in a.parser.lexicon.surface_forms:
            nsfidx = a.parser.lexicon.surface_forms.index(key[0])
        if nsfidx is not None:
            syn = [nsfidx, a.parser.lexicon.semantic_forms[nsfidx]]
    return syn

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
