#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('/u/jesse/phm/tsp/')  # necessary to import CKYParser from above directory

import argparse
import copy
import math
import numpy as np
import pickle
import random


def main():

    # Load parameters from command line.
    agent_infile = FLAGS_agent_infile
    parse_reranker_beam = FLAGS_parse_reranker_beam
    interpolation_reranker_beam = FLAGS_interpolation_reranker_beam
    pairs_infile = FLAGS_pairs_infile
    pair_idx = FLAGS_pair_idx
    outfile = FLAGS_outfile
    x = FLAGS_x
    g = FLAGS_g

    # Load the parser and prepare the pair.
    with open(agent_infile, 'rb') as f:
        a = pickle.load(f)
    if x is None and g is None:
        with open(pairs_infile, 'rb') as f:
            pairs = pickle.load(f)
        x, g = pairs[pair_idx]
    else:
        g = a.parser.lexicon.read_semantic_form_from_str(g, None, None, [])

    print ("get_semantic_forms_for_induced_pairs: looking for semantic forms for x '" + str(x) +
           "' with grounding " + a.parser.print_parse(g))

    utterance_semantic_pairs = None
    parses = []
    cky_parse_generator = a.parser.most_likely_cky_parse(x, reranker_beam=parse_reranker_beam,
                                                         debug=False)
    cgtr = a.call_generator_with_timeout(cky_parse_generator, None)  # a.budget_for_parsing)
    parse = None
    if cgtr is not None:
        parse = cgtr[0]
        score = cgtr[1]  # most_likely_cky_parse returns a 4-tuple headed by the parsenode and score
    latent_forms_considered = 1
    while (parse is not None and len(parses) < interpolation_reranker_beam and
           latent_forms_considered < a.latent_forms_to_consider_for_induction):

        print ("get_semantic_forms_for_induced_pairs: ... grounding semantic form " +
               a.parser.print_parse(parse.node, True) + " with scores p " + str(score))
        gs = a.call_function_with_timeout(a.grounder.ground_semantic_tree, {"root": parse.node},
                                          None)  # a.budget_for_grounding)
        if gs is not None:
            gn = a.sort_groundings_by_conf(gs)
        else:
            gn = []
        if len(gn) > 0:
            for gz, g_score in gn:
                print ("get_semantic_forms_for_induced_pairs: ...... form grounded to " +
                       str(a.parser.print_parse(gz) if type(gz) is not bool else str(gz)) + " with score " +
                       str(g_score))
                if ((type(gz) is bool and gz == g) or
                        (type(gz) is not bool and g.equal_allowing_commutativity(gz, a.parser.ontology))):
                    parses.append([parse, score + math.log(g_score + 1.0)])  # add 1 for zero probabilities
                    print ("get_semantic_forms_for_induced_pairs: ... found semantic form " +
                           a.parser.print_parse(parse.node, True) +
                           " with scores p " + str(score) + ", g " + str(g_score))
                    break  # break here since groundings below this, even if they match, will have lower score

        cgtr = a.call_generator_with_timeout(cky_parse_generator, None)  # a.budget_for_parsing)
        parse = None
        if cgtr is not None:
            parse = cgtr[0]
            score = cgtr[1]

        latent_forms_considered += 1

    if len(parses) > 0:
        sorted_interpolation = sorted(parses, key=lambda t: t[1], reverse=True)
        best_interpolated_parses = [parse for parse, score in sorted_interpolation
                                    if np.isclose(score, sorted_interpolation[0][1])]
        best_interpolated_parse = random.choice(best_interpolated_parses)
        print ("get_semantic_forms_for_induced_pairs: ... re-ranked to choose " +
               a.parser.print_parse(best_interpolated_parse.node))
        best_interpolated_parse.node.commutative_lower_node(a.parser.ontology)
        print ("get_semantic_forms_for_induced_pairs: ... commutative lowered to " +
               a.parser.print_parse(best_interpolated_parse.node))
        utterance_semantic_pairs = [[x, a.parser.print_parse(best_interpolated_parse.node, True), g]]
    elif len(a.parser.tokenize(x)) <= a.parser.max_multiword_expression:
        # Find the categories of entries in lexicon, if any, matching g.
        matching_categories = []
        for surface_idx in range(len(a.parser.lexicon.surface_forms)):
            for sem_idx in a.parser.lexicon.entries[surface_idx]:
                if g.equal_allowing_commutativity(a.parser.lexicon.semantic_forms[sem_idx],
                                                  a.parser.ontology, ignore_syntax=True):
                    matching_categories.append(a.parser.lexicon.semantic_forms[sem_idx].category)
        if len(matching_categories) > 0:
            utterance_semantic_pairs = []
            for c in matching_categories:
                print ("get_semantic_forms_for_induced_pairs: no semantic parse found; adding possible synonymy pair " +
                       "'" + str(x) + "' with " + a.parser.lexicon.compose_str_from_category(c) + " : " +
                       a.parser.print_parse(g))
                parse = copy.deepcopy(g)
                parse.category = c
                utterance_semantic_pairs.append([x, a.parser.print_parse(parse, True), g])
    else:
        print ("get_semantic_forms_for_induced_pairs: no semantic parse found matching " +
               "grounding for pair '" + str(x) + "', " + a.parser.print_parse(g))

    with open(outfile, 'wb') as f:
        pickle.dump(utterance_semantic_pairs, f)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent_infile', type=str, required=True,
                        help="the agent pickle")
    parser.add_argument('--parse_reranker_beam', type=int, required=True,
                        help="how many parses to re-rank internally before returning")
    parser.add_argument('--interpolation_reranker_beam', type=int, required=True,
                        help="how many parse+grounding scores to beam down before reranking")
    parser.add_argument('--pairs_infile', type=str, required=True,
                        help="the pairs pickle")
    parser.add_argument('--pair_idx', type=int, required=True,
                        help="the pair idx in the pairs_infile pickle this thread will process")
    parser.add_argument('--outfile', type=str, required=True,
                        help="where to dump new pair information")
    parser.add_argument('--x', type=str, required=False,
                        help="the utterance as a string")
    parser.add_argument('--g', type=str, required=False,
                        help="the grounding as a string")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
