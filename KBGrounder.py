#!/usr/bin/env python
__author__ = 'jesse'

import sys
import copy
import KnowledgeBase


class KBGrounder:

    def __init__(self, ontology, static_facts_fn, perception_source_dir, perception_feature_dir):
        self.ontology = ontology
        self.parser = None
        self.static_kb = KnowledgeBase.KnowledgeBase(static_facts_fn, perception_source_dir, perception_feature_dir)
        pass

    # returns possible groundings for given semantic node
    def ground_semantic_node(self, root, lambda_names, lambda_types, lambda_assignments):
        debug = False

        groundings = []
        if debug:
            print ("grounding " + self.parser.print_parse(root, True) + " with " + str(lambda_names) + "," +
                   str(lambda_types) + "," + str(lambda_assignments))

        # if lambda, index and try assignments on children
        if root.is_lambda and root.is_lambda_instantiation:
            if debug:
                print "root is lambda"
            new_names = lambda_names[:]
            new_names.append(root.lambda_name)
            new_types = lambda_types[:]
            new_types.append(root.type)
            for assignment in self.assignments_for_type(root.type):
                new_assignments = lambda_assignments[:]
                new_assignments.append(assignment)
                grounding_results = self.ground_semantic_node(root.children[0], new_names, new_types, new_assignments)
                for gr in grounding_results:
                    if gr[1]:  # satisfied with this assignment, so pass up
                        groundings.append(gr)
            if debug:
                print "lambda groundings: "+str(groundings)  # DEBUG
            return groundings

        # if lambda instance, make given assignment and return
        elif root.is_lambda and not root.is_lambda_instantiation:
            if debug:
                print "root is lambda instance"
            if root.children is None:  # lambda leaf
                return [self.ontology.preds[lambda_assignments[lambda_names.index(root.lambda_name)]]]
            else:  # lambda predicate
                replaced = copy.deepcopy(root)
                replaced.is_lambda = False
                replaced.is_lambda_instantiation = False
                replaced.lambda_name = None
                replaced.idx = lambda_assignments[lambda_names.index(root.lambda_name)]
                if debug:
                    print "grounding lambda predicate instance as "+self.ontology.preds[replaced.idx]
                return self.ground_semantic_node(replaced, lambda_names, lambda_types, lambda_assignments)

        # leaf predicate/atom
        elif root.children is None:
            if debug:
                print "root is leaf predicate. Will return ", str([self.ontology.preds[root.idx]])
            return [self.ontology.preds[root.idx]]

        # if type is predicate, ground arguments and evaluate
        else:
            if debug:
                print "root is predicate"
            child_grounds = []
            for c in root.children:
                child_grounds.append(self.ground_semantic_node(c, lambda_names, lambda_types, lambda_assignments))
            if debug:
                print self.ontology.preds[root.idx]+" child grounds: "+str(child_grounds)  # DEBUG
            # for every combination of child groundings we resolve and return a different grounding
            child_ground_idx = [0 for _ in range(len(child_grounds))]
            while True:

                if min([len(cg) for cg in child_grounds]) == 0:
                    break  # unsatisfiable child(ren)

                # if logical predicate, handle here
                if self.ontology.preds[root.idx] == 'equals':
                    to_match = grounding_to_answer_set(child_grounds[0][child_ground_idx[0]])
                    satisfied = None
                    confidence = child_grounds[0][2]
                    for i in range(1, len(root.children)):
                        child_to_match = grounding_to_answer_set(child_grounds[i][child_ground_idx[i]])
                        confidence *= child_grounds[i][2]
                        if to_match != child_to_match:
                            satisfied = False
                    if satisfied is None:
                        satisfied = True
                elif self.ontology.preds[root.idx] == 'and':
                    satisfied = grounding_to_answer_set(child_grounds[0][child_ground_idx[0]])
                    confidence = child_grounds[0][2]
                    for i in range(1, len(root.children)):
                        if satisfied != grounding_to_answer_set(child_grounds[i][child_ground_idx[i]]):
                            satisfied = False
                        confidence *= child_grounds[i][2]
                elif self.ontology.preds[root.idx] == 'or':
                    satisfied = False
                    confidence = 1.0
                    for i in range(len(root.children)):
                        if grounding_to_answer_set(child_grounds[i][child_ground_idx[i]]) is not False:
                            satisfied = grounding_to_answer_set(child_grounds[i][child_ground_idx[i]])
                        confidence *= child_grounds[i][2]
                elif self.ontology.preds[root.idx] == 'the':
                    if debug:
                        print "'the' child grounds to inspect: " + str(child_grounds[0][child_ground_idx[0]])  # DEBUG
                    if (len(child_grounds[0]) == 1 and
                            len(lambda_assignments) < len(child_grounds[0][child_ground_idx[0]][0])):
                        # set satisfied to the satisfying lambda arg that heads child
                        satisfied = child_grounds[0][child_ground_idx[0]][0][len(lambda_assignments)]
                    else:
                        satisfied = False
                    confidence = child_grounds[0][2]
                elif self.ontology.preds[root.idx] == 'a':
                    if debug:
                        print "'a' child grounds to inspect: " + str(child_grounds[0][child_ground_idx[0]])  # DEBUG
                    if len(child_grounds[0]) > 0:
                        # set satisfies, so choose arbitrary element to return (here, first)
                        # TODO: sort by confidence and return highest-confidence instead of arbitrary
                        if type(child_grounds[0][child_ground_idx[0]]) is list:
                            satisfied = child_grounds[0][child_ground_idx[0]][0][len(lambda_assignments)]
                        elif type(child_grounds[0][child_ground_idx[0]]) is str:
                            satisfied = child_grounds[0][child_ground_idx[0]]
                        else:
                            sys.exit("ERROR: grounding 'a' failed; unexpected child ground entry " +
                                     str(child_grounds[0][child_ground_idx[0]]))
                    else:
                        satisfied = False
                    confidence = child_grounds[0][2]

                # if KB predicate, query
                else:
                    if debug:
                        print "detected KB predicate "+self.ontology.preds[root.idx]  # DEBUG
                    ql = [self.ontology.preds[root.idx]]
                    for i in range(len(root.children)):
                        # take the first grounding result from the set if it is multi-element
                        # TODO: inspect when this happens because it sounds fishy
                        ql.append(grounding_to_answer_set(child_grounds[i])[0])
                    q = tuple(ql)
                    satisfied, confidence = self.static_kb.query(q)

                # add to groundings if successful
                if satisfied:
                    groundings.append([[self.ontology.preds[i] for i in lambda_assignments], satisfied, confidence])

                    # 'a' predicate has a restriction to return only a singleton, so exit as soon as something is added
                    if self.ontology.preds[root.idx] == 'a':
                        break

                # iterate idx counter to try new grounding terms
                max_idx = [0 for _ in range(len(child_ground_idx))]
                for i in range(len(child_ground_idx)):
                    child_ground_idx[i] += 1
                    if child_ground_idx[i] == len(child_grounds[i]):
                        child_ground_idx[i] = 0
                        max_idx[i] = 1
                    else:
                        break
                if sum(max_idx) == len(root.children):
                    break
            if debug:
                print "groundings (root "+self.ontology.preds[root.idx]+"): "+str(groundings)  # DEBUG
            return groundings

    # returns all possible ontological assignments to lambdas of a given type
    def assignments_for_type(self, t):
        return [i for i in range(len(self.ontology.preds)) if self.ontology.entries[i] == t]


# take in a semantic grounding list and return an answer set
def grounding_to_answer_set(g):
    if type(g) is list:
        if len(g) == 0:
            return []
        if type(g[0]) is str:
            return g
        if len(g) == 2 and type(g[0]) is list and type(g[1]) is str:
            return g[1]
        return [gr[1] for gr in g]
    else:
        return g
