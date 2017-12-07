#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('/u/jesse/phm/tsp/')  # necessary to import CKYParser from above directory

import argparse
import math
import pickle


def main():

    # Load parameters from command line.
    agent_infile = FLAGS_agent_infile
    parse_reranker_beam = FLAGS_parse_reranker_beam
    interpolation_reranker_beam = FLAGS_interpolation_reranker_beam
    pairs_infile = FLAGS_pairs_infile
    pair_idx = FLAGS_pair_idx
    outfile = FLAGS_outfile

    # Load the parser and prepare the pair.
    with open(agent_infile, 'rb') as f:
        a = pickle.load(f)
    with open(pairs_infile, 'rb') as f:
        pairs = pickle.load(f)
    x, g = pairs[pair_idx]

    print ("get_semantic_forms_for_induced_pairs: looking for semantic forms for x '" + str(x) +
           "' with grounding " + a.parser.print_parse(g))

    utterance_semantic_pair = None
    parses = []
    cky_parse_generator = a.parser.most_likely_cky_parse(x, reranker_beam=parse_reranker_beam,
                                                         debug=False)
    cgtr = a.call_generator_with_timeout(cky_parse_generator, a.budget_for_parsing)
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
                                          a.budget_for_grounding)
        if gs is not None:
            gn = a.sort_groundings_by_conf(gs)
        else:
            gn = []
        if len(gn) > 0:
            gz, g_score = gn[0]  # top confidence grounding, which may be True/False
            if ((type(gz) is bool and gz == g) or
                    (type(gz) is not bool and g.equal_allowing_commutativity(gz, a.parser.ontology))):
                parses.append([parse, score + math.log(g_score + 1.0)])  # add 1 for zero probabilities
                print ("get_semantic_forms_for_induced_pairs: ... found semantic form " +
                       a.parser.print_parse(parse.node, True) +
                       " with scores p " + str(score) + ", g " + str(g_score))
            cgtr = a.call_generator_with_timeout(cky_parse_generator, a.budget_for_parsing)
            parse = None
            if cgtr is not None:
                parse = cgtr[0]
                score = cgtr[1]
        latent_forms_considered += 1

    if len(parses) > 0:
        best_interpolated_parse = sorted(parses, key=lambda t: t[1], reverse=True)[0][0]
        utterance_semantic_pair = [x, best_interpolated_parse.node]
        print "... re-ranked to choose " + a.parser.print_parse(best_interpolated_parse.node)
    else:
        print ("get_semantic_forms_for_induced_pairs: no semantic parse found matching " +
               "grounding for pair '" + str(x) + "', " + a.parser.print_parse(g))

    with open(outfile, 'wb') as f:
        pickle.dump(utterance_semantic_pair, f)


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
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
