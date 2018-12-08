#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../../tsp')  # necessary to use Ontology, Lexicon, CKYParser, etc.
sys.path.append('../')  # necessary to import Agent, IO from above directory

import argparse
import pickle
import os
import Agent
import KBGrounder
import IO


def main():

    # Load parameters from command line.
    agg_fns = FLAGS_agg_fns.split(',')
    parser_fn = FLAGS_parser_fn
    embeddings_fn = FLAGS_embeddings_fn
    parser_outfile = FLAGS_parser_outfile
    parser_base_pairs_fn = FLAGS_parser_base_pairs_fn
    only_use_base_pairs = True if FLAGS_only_use_base_pairs == 1 else False
    kb_static_facts_fn = FLAGS_kb_static_facts_fn
    kb_perception_feature_dir = FLAGS_kb_perception_feature_dir
    kb_perception_source_base_dir = FLAGS_kb_perception_source_base_dir
    kb_perception_source_target_dir = FLAGS_kb_perception_source_target_dir
    active_test_set = [int(oidx) for oidx in FLAGS_active_test_set.split(',')]
    only_bare_nouns = True if FLAGS_only_bare_nouns == 1 else False
    training_log_fn = FLAGS_training_log_fn
    full_pairs_log_fn = FLAGS_full_pairs_log_fn
    epochs = FLAGS_epochs
    use_condor = FLAGS_use_condor
    condor_target_dir = FLAGS_condor_target_dir
    condor_parser_script_dir = FLAGS_condor_parser_script_dir
    condor_grounder_script_dir = FLAGS_condor_grounder_script_dir
    assert not use_condor or (condor_target_dir is not None and condor_parser_script_dir is not None
                              and condor_grounder_script_dir is not None)

    # Load the aggregate information from file
    print("main: loading aggregate conversation files...")
    agg_all_utterances = []
    agg_role_utterances_role_chosen_pairs = []
    agg_perceptual_labels = []
    agg_perceptual_synonymy = []
    agg_all_parser_timeouts = []  # Don't currently do anything with this timeout data in this script.
    agg_all_grounder_timeouts = []
    for agg_fn in agg_fns:
        print("main: ... loading from '" + agg_fn + "'")
        with open(agg_fn, 'rb') as f:
            _agg_all_utterances, _agg_role_utterances_role_chosen_pairs, _agg_perceptual_labels,\
                _agg_perceptual_synonymy, _agg_all_parser_timeouts, _agg_all_grounder_timeouts = pickle.load(f)
            agg_all_utterances.extend(_agg_all_utterances)
            agg_role_utterances_role_chosen_pairs.extend(_agg_role_utterances_role_chosen_pairs)
            agg_perceptual_labels.extend(_agg_perceptual_labels)
            agg_perceptual_synonymy.extend(_agg_perceptual_synonymy)
            agg_all_parser_timeouts.append(_agg_all_parser_timeouts)
            agg_all_grounder_timeouts.append(_agg_all_grounder_timeouts)
    print("... done")

    # Load a grounder from file
    print("main: loading base parser from file...")
    with open(parser_fn, 'rb') as f:
        p = pickle.load(f)
        p.lexicon.wv = None
        if embeddings_fn is not None:
            print("main: ... adding embeddings")
            p.lexicon.wv = p.lexicon.load_word_embeddings(embeddings_fn)
    print("main: ... done")

    # Load parser base pairs, if any.
    print("main: loading base parser pairs from file...")
    if parser_base_pairs_fn is not None:
        parser_base_pairs = p.read_in_paired_utterance_semantics(parser_base_pairs_fn)
    else:
        parser_base_pairs = []
    print("main: ... done")

    # Copy the base grounder labels.pickle and predicates.pickle into the target directory.
    print("main: copying base KB perception labels and pickles to target dir...")
    base_labels_fn = os.path.join(kb_perception_source_base_dir, "labels.pickle")
    base_pickles_fn = os.path.join(kb_perception_source_base_dir, "predicates.pickle")
    if os.path.isfile(base_labels_fn):
        os.system("cp " + base_labels_fn + " " + os.path.join(kb_perception_source_target_dir, "labels.pickle"))
    else:
        print("ERROR: file not found '" + base_labels_fn + "'")
        return 1
    if os.path.isfile(base_pickles_fn):
        os.system("cp " + base_pickles_fn + " " + os.path.join(kb_perception_source_target_dir, "predicates.pickle"))
    else:
        print("ERROR: file not found '" + base_pickles_fn + "'")
        return 1
    print("main: ... done")

    # Instantiate a new grounder with the base parser and with perception source at the target dir.
    print("main: instantiating grounder...")
    g = KBGrounder.KBGrounder(p, kb_static_facts_fn, kb_perception_source_target_dir,
                              kb_perception_feature_dir, active_test_set)
    print("main: ... done")

    # Instantiate vestigial input/output
    print("main: instantiating basic IO...")
    io = IO.KeyboardIO()
    print("main: ... done")

    # Instantiate an Agent.
    print("main: instantiating Agent...")
    a = Agent.Agent(p, g, io, None)
    print("main: ... done")

    # Open logfile.
    log_f = open(training_log_fn, 'w')

    # Look through aggregated labels to identify good perceptual candidates.
    preds_by_label = {}
    for pred, oidx, l in agg_perceptual_labels:
        if pred not in preds_by_label:
            preds_by_label[pred] = {}
        if oidx not in preds_by_label[pred]:
            preds_by_label[pred][oidx] = 0
        preds_by_label[pred][oidx] += 1 if l else -1
    # print "main: preds_by_label: " + str(preds_by_label)
    preds_by_oidx_label = {}
    for pred in preds_by_label:
        preds_by_oidx_label[pred] = {True: [], False: []}
        for oidx in preds_by_label[pred]:
            if preds_by_label[pred][oidx] > 0:
                preds_by_oidx_label[pred][True].append(oidx)
            elif preds_by_label[pred][oidx] < 0:
                preds_by_oidx_label[pred][False].append(oidx)
    # print "main: preds_by_oidx_label: " + str(preds_by_oidx_label)
    preds_w_pos = [pred for pred in preds_by_oidx_label if len(preds_by_oidx_label[pred][True]) > 0]
    print("main: preds_w_pos: " + str(preds_w_pos))

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
    print("main: synonymy votes: " + str(synonymy_votes))
    synonymy_candidates = {key: synonymy_votes[key] for key in synonymy_votes.keys() if synonymy_votes[key] > 0}
    print("main: synonymy candidates: " + str(synonymy_candidates))

    # Decide based on synonymy and pred labels which lexicon entries to add (similar to procedure in Agent.py,
    # but based on voting instead of single-user feedback.)
    all_preds = list(set([pred for pred, _, _ in agg_perceptual_labels] +
                     [pred for pred, _ in synonymy_votes.keys()] +
                     [pred for _, pred in synonymy_votes.keys()]))
    preds = [pred for pred in all_preds if pred not in a.parser.lexicon.surface_forms and
             (pred in preds_w_pos or len([synp for synp in preds_w_pos if (pred, synp) in synonymy_candidates
                                         or (synp, pred) in synonymy_candidates])) > 0]
    print("main: preds to consider: " + str(preds))
    utterances_with_pred = {}
    for pred in all_preds:
        utterances_with_pred[pred] = []
        for u in agg_all_utterances:
            if pred in a.parser.tokenize(u):
                utterances_with_pred[pred].append(u)
    # print "main: utterances with preds: " + str(utterances_with_pred)

    # Iterate over pedicates to identify likely adjectives (those left of other already-known predicates).
    # This process should repeat until no further adjectives around found (allowing chaining unseen adjs).
    # Afterwards, any predicate not flagged as an adjective is probably a noun (no percept neighbors to the right).
    pred_is_perc = {pred: False for pred in preds}
    new_perceptual_adds = True
    known_perc_preds = [tk for tk in a.parser.lexicon.surface_forms if a.is_token_perceptual(tk)]
    print("main: known perceptual preds: " + str(known_perc_preds))
    while new_perceptual_adds:
        new_perceptual_adds = False
        print("main: checking for new adjectives and nouns...")
        for pred in preds:
            print("main: considering '" + pred + "' with pred_is_perc=" +
                  str(pred_is_perc[pred]) + " and num utt " + str(len(utterances_with_pred[pred])))
            if not pred_is_perc[pred] and len(utterances_with_pred[pred]) > 0:
                syn = get_syn_from_candidates(a, pred, synonymy_candidates)

                if only_bare_nouns:

                    # Add bare nouns, later type-raise.
                    a.add_new_perceptual_lexical_entries(pred, False, syn)
                    print("main: added noun for '" + pred + "'")
                    if syn is not None:
                        print("main: ... with known synonym '" + a.parser.lexicon.surface_forms[syn[0]] + "'")
                    log_f.write("added noun entry for '" + pred + "' with synonym " +
                                str(a.parser.lexicon.surface_forms[syn[0]] if syn is not None else None) + "\n")

                else:

                    # Turkers tend to use malformed language, so add all new preds as both adjectives and nouns.
                    if True:
                        pred_is_perc[pred] = True
                        new_perceptual_adds = True
                        ont_pred = a.add_new_perceptual_lexical_entries(pred, True, syn)
                        a.add_new_perceptual_lexical_entries(pred, False, syn, ont_pred)
                        print("main: added noun and adjective for '" + pred + "'")
                        if syn is not None:
                            print("main: ... with known synonym '" + a.parser.lexicon.surface_forms[syn[0]] + "'")
                        log_f.write("added adjective and noun entry for '" + pred + "' with synonym " +
                                    str(a.parser.lexicon.surface_forms[syn[0]] if syn is not None else None) + "\n")

                    # Determine whether each predicate is mostly behaving like a noun or adjective before adding.
                    else:
                        # Just count how often a pred is 'acting' like an adjective or noun based on position.
                        la = ln = 0
                        for u in utterances_with_pred[pred]:
                            tks = a.parser.tokenize(u)
                            tkidx = tks.index(pred)
                            if tkidx < len(tks) - 1 and (tks[tkidx + 1] in known_perc_preds
                                                         or tks[tkidx + 1] in all_preds
                                                         or tks[tkidx + 1] not in a.parser.lexicon.surface_forms):
                                la += 1
                            elif tkidx == len(tks) - 1 or tks[tkidx + 1] in a.parser.lexicon.surface_forms:
                                ln += 1
                        la /= float(len(utterances_with_pred[pred]))
                        ln /= float(len(utterances_with_pred[pred]))

                        if la > 0.5:
                            pred_is_perc[pred] = True
                            new_perceptual_adds = True
                            a.add_new_perceptual_lexical_entries(pred, True, syn)

                            print("main: added adjective '" + pred + "'")
                            if syn is not None:
                                print("main: ... with known synonym '" + a.parser.lexicon.surface_forms[syn[0]] + "'")
                            log_f.write("added adjective '" + pred + "' with synonym " + str(syn) + "\n")

                        elif ln > 0.5:
                            pred_is_perc[pred] = True
                            new_perceptual_adds = True
                            a.add_new_perceptual_lexical_entries(pred, False, syn)

                            print("main: added noun '" + pred + "'")
                            if syn is not None:
                                print("main: ... with known synonym '" + a.parser.lexicon.surface_forms[syn[0]] + "'")
                            log_f.write("added noun '" + pred + "' with synonym " + str(syn) + "\n")
    if only_bare_nouns:
        a.parser.type_raise_bare_nouns()  # should only affect new nouns
        a.parser.theta.update_probabilities()  # because the above adds new entries
    print("main: ... done")

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
    log_f.write("updated classifiers with " + str(len(upidxs)) + " new labels across " +
                str(len(set(upidxs))) + " predicates...\n")
    print("main: ... done")

    # Write new classifiers to file.
    print("main: committing grouder classifiers to file...")
    g.kb.pc.commit_changes()  # save classifiers to disk
    print("main: ... done")

    # Induce pairs from agg data.
    print("main: ... creating induced pairs from aggregated conversations...")
    for action_confirmed, user_utterances_by_role in agg_role_utterances_role_chosen_pairs:
        new_i_pairs = a.induce_utterance_grounding_pairs_from_conversation(user_utterances_by_role,
                                                                           action_confirmed)
        a.induced_utterance_grounding_pairs.extend(new_i_pairs)
    print("main: ...... done; induced " + str(len(a.induced_utterance_grounding_pairs)) + " pairs")
    log_f.write("induced " + str(len(a.induced_utterance_grounding_pairs)) + " utterance/grounding pairs\n")

    # DEBUG - write the Agent out to file for use by other scripts
    with open("agent.temp.pickle", 'wb') as f:
        pickle.dump(a, f)
    # END DEBUG

    # Iterate inducing new pairs using most up-to-date parser and training for single epoch.
    # Each of these stages can be distributed over the UT Condor system for more linear-time computation.
    print("main: training parser by alternative grounding->semantics and semantics->parser training steps...")
    fplfn = open(full_pairs_log_fn, 'w')
    for epoch in range(epochs):

        # Get grouding->semantics pairs
        if not only_use_base_pairs:
            print("main: ... getting utterance/semantic form pairs from induced utterance/grounding pairs...")
            utterance_semantic_grounding_triples = a.get_semantic_forms_for_induced_pairs(
                1, 10, verbose=1, use_condor=use_condor, condor_target_dir=condor_target_dir,
                condor_script_dir=condor_grounder_script_dir)
            print ("main: ...... got " + str(len(utterance_semantic_grounding_triples)) + " utterance/semantics " +
                   "pairs from induced utterance/grounding pairs")
            log_f.write("epoch " + str(epoch) + ": got " + str(len(utterance_semantic_grounding_triples)) +
                        " utterance/semantic pairs\n")

            # Write out induced pairs to logfile(s) for later inspection and qualitative analysis.
            fplfn.write("epoch " + str(epoch) + ":\n\n" +
                        '\n\n'.join(['\n'.join([x, a.parser.print_parse(y, True),
                                                a.parser.print_parse(z, False)])
                                     for x, y, z in utterance_semantic_grounding_triples])
                        + '\n\n')
        else:
            utterance_semantic_grounding_triples = []

        # Write the new parser to file.
        print("main: writing current re-trained parser to file...")
        with open(parser_outfile + "." + str(epoch), 'wb') as f:
            pickle.dump(p, f)
        print("main: ... done")

        # Train parser on utterances->semantics pairs
        print("main: ... re-training parser on pairs induced from aggregated conversations...")
        utterance_semantic_pairs = [[x, y] for x, y, _ in utterance_semantic_grounding_triples]
        perf = []
        a.parser.train_learner_on_semantic_forms(parser_base_pairs + utterance_semantic_pairs,
                                                 epochs=1, epoch_offset=epoch, reranker_beam=1, verbose=2,
                                                 use_condor=use_condor, condor_target_dir=condor_target_dir,
                                                 condor_script_dir=condor_parser_script_dir,
                                                 perf_log=perf)
        log_f.write("epoch " + str(epoch) + ": parser trained on " + str(perf[0][0]) + " examples and " +
                    "failed on " + str(perf[0][1]) + " out of " +
                    str(len(parser_base_pairs) + len(utterance_semantic_pairs)) + "\n")

    # Write the final parser to file.
    print("main: writing current re-trained parser to file...")
    with open(parser_outfile + ".final", 'wb') as f:
        pickle.dump(p, f)
    print("main: ... done")

    fplfn.close()
    print("main: ... done")

    # Close logfile.
    log_f.close()


def get_syn_from_candidates(a, pred, synonymy_candidates):
    for key in synonymy_candidates:
        nsfidx = None
        if key[0] == pred and key[1] in a.parser.lexicon.surface_forms:
            nsfidx = a.parser.lexicon.surface_forms.index(key[1])
        elif key[1] == pred and key[0] in a.parser.lexicon.surface_forms:
            nsfidx = a.parser.lexicon.surface_forms.index(key[0])
        if nsfidx is not None:
            forms = []
            for sem_idx in a.parser.lexicon.entries[nsfidx]:
                psts = a.get_parse_subtrees(a.parser.lexicon.semantic_forms[sem_idx],
                                            a.grounder.kb.perceptual_preds)
                if len(psts) > 0:
                    forms.extend(psts)
            return [nsfidx, forms]
    return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--agg_fns', type=str, required=True,
                        help="the aggregated data pickles for the users to use as retraining material")
    parser.add_argument('--parser_fn', type=str, required=True,
                        help="a parser base pickle to load")
    parser.add_argument('--embeddings_fn', type=str, required=False,
                        help="embeddings to use during training, if any")
    parser.add_argument('--parser_outfile', type=str, required=True,
                        help="where to store the newly-trained parser")
    parser.add_argument('--parser_base_pairs_fn', type=str, required=False,
                        help="base utterance/semantic training pairs, if any, to append to parser for training")
    parser.add_argument('--only_use_base_pairs', type=int, required=False, default=0,
                        help="if 1, only consider base pairs and don't induce new data from aggregation")
    parser.add_argument('--kb_static_facts_fn', type=str, required=True,
                        help="static facts file for the knowledge base")
    parser.add_argument('--kb_perception_feature_dir', type=str, required=True,
                        help="perception feature directory for knowledge base")
    parser.add_argument('--kb_perception_source_base_dir', type=str, required=True,
                        help="perception source directory for the base KB")
    parser.add_argument('--kb_perception_source_target_dir', type=str, required=True,
                        help="perception source directory for the target KB after retraining")
    parser.add_argument('--active_test_set', type=str, required=True,
                        help="objects to consider possibilities for grounding")
    parser.add_argument('--only_bare_nouns', type=int, required=True,
                        help="whether to use only bare nouns or nouns/adjectives")
    parser.add_argument('--training_log_fn', type=str, required=True,
                        help="logfile to write training epoch information out to")
    parser.add_argument('--full_pairs_log_fn', type=str, required=True,
                        help="logfile to write utterance/semantic/grounding triples to")
    parser.add_argument('--epochs', type=int, required=False, default=10,
                        help="how many times to iterate over grounding/parsing data")
    parser.add_argument('--use_condor', type=int, required=False, default=0,
                        help="whether to invoke the UT condor system to distribute parser training")
    parser.add_argument('--condor_target_dir', type=str, required=False, default=None,
                        help="directory to write condor files")
    parser.add_argument('--condor_parser_script_dir', type=str, required=False, default=None,
                        help="path to TSP condor help scripts")
    parser.add_argument('--condor_grounder_script_dir', type=str, required=False, default=None,
                        help="path to grounded mturk condor help scripts")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
