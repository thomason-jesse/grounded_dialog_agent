#!/usr/bin/env python
__author__ = 'jesse'

import copy
import KnowledgeBase
import signal
import time

class KBGrounder:

    # parser - an instance of CKYParser
    # static_facts_fn - a filename for a static facts plain text file
    # perception_source_dir - the directory for perception source containing predicates, labels, and trained classifiers
    # perception_feature_dir - the directory for perception containing oidxs and object features
    # active_test_set - a list of oidxs to consider as test objects (labels ignored during SVM training/testing)
    def __init__(self, parser, static_facts_fn,
                 perception_source_dir, perception_feature_dir,
                 active_test_set):
        self.parser = parser
        self.kb = KnowledgeBase.KnowledgeBase(static_facts_fn, perception_source_dir, perception_feature_dir,
                                              active_test_set, parser.ontology)
        self.active_test_set = active_test_set

    # Given a semantic tree, return a list of trees with the lambdas of the original tree filled by every possible
    # grounding that satisfies those lambdas.
    def ground_semantic_tree(self, root):
        debug = False
        if debug:
            print("ground_semantic_tree: grounding at root " + self.parser.print_parse(root))

        start_time = time.time()

        # If the head of the tree is a lambda instantiation, add candidates for all its possible fills.
        # Every grounding entry is a tuple of a tree (or bool), the lambda values instantiated at and below root,
        # and a confidence.
        groundings = []
        if root.is_lambda_instantiation:
            for assignment in self.assignments_for_type(root.type):  # assignments are ont pred idxs

                # Form candidate sub-tree with this assignment instantiated.
                candidate = copy.deepcopy(root.children[0])
                self.instantiate_lambda(candidate, root.lambda_name, assignment)

                # Call this grounding routine on the candidate to get finished products.
                candidate_groundings = self.ground_semantic_tree(candidate)
                if candidate_groundings is None:
                    return None
                groundings.extend([(cg, [assignment] + la, conf) for cg, la, conf in candidate_groundings])


        # If the head of the tree is a predicate (e.g. has any children), we need to ground those children
        # and then apply the predicate's operation to them.
        elif root.children is not None:
            root.set_return_type(self.parser.ontology)

            # Get forms of this tree with children grounded, then apply the predicate to those grounded
            # children to return appropriately.
            child_groundings = []
            for c in root.children:
                result = self.ground_semantic_tree(c)
                if result is None:
                    return None
                child_groundings.append(result)
            child_groundings = [self.ground_semantic_tree(c) for c in root.children]
            if debug:
                print("ground_semantic_tree: for root " + self.parser.print_parse(root) + ", child_groundings: " +
                      str(child_groundings))

            # Logical predicates.
            if self.is_logical(root.idx, 'equals'):
                # Return instances of ground child trees that match.
                for cidx in range(len(child_groundings[0])):
                    ci_tree = child_groundings[0][cidx][0]
                    ci_la = child_groundings[0][cidx][1]
                    conf = child_groundings[0][cidx][2]
                    for cjdx in range(len(child_groundings[1])):  # equals takes two children
                        cj_tree = child_groundings[1][cjdx][0]
                        cj_la = child_groundings[1][cjdx][1]
                        conf *= child_groundings[1][cjdx][2]
                        if ci_tree.equal_allowing_commutativity(cj_tree, self.parser.ontology,
                                                                ignore_syntax=True):
                            match = copy.deepcopy(root)
                            match.children = [ci_tree, cj_tree]
                            groundings.append((match, ci_la + cj_la, conf))

            elif self.is_logical(root.idx, 'and'):
                if debug:
                    print ("ground_semantic_tree: processing 'and' root")
                if len(child_groundings) < 2:
                    print ("WARNING: KBGrounder found 'and' with only one child: " +
                           self.parser.print_parse(root, True))
                # Return True bool if ground child trees' boolean values match.
                cc_lc = []  # child combinations at length c for c the idx
                lc_0 = []  # idxs of children for whom 'and' holds
                for cidx in range(len(child_groundings[0])):
                    lc_0.append([cidx])
                cc_lc.append(lc_0)
                for cj in range(1, len(child_groundings)):
                    lc_j = []
                    for comb in cc_lc[cj - 1]:
                        ci_bool = child_groundings[0][comb[0]][0]
                        for cjdx in range(len(child_groundings[cj])):  # and takes arbitrarily many children
                            cj_bool = child_groundings[cj][cjdx][0]
                            if ci_bool == cj_bool:
                                lc_j.append(comb + [cjdx])
                    cc_lc.append(lc_j)
                for comb in cc_lc[len(child_groundings) - 1]:
                    if len(comb) == len(child_groundings):
                        match = child_groundings[0][comb[0]][0]
                        la_ext = child_groundings[0][comb[0]][1][:]
                        conf = child_groundings[0][comb[0]][2]
                        for idx in range(1, len(comb)):
                            la_ext.extend(child_groundings[idx][comb[idx]][1][:])
                            conf *= child_groundings[idx][comb[idx]][2]
                        groundings.append((match, la_ext, conf))

            elif self.is_logical(root.idx, 'or'):
                # TODO: implement 'or' similar to 'and' but returning all matches with at least one true child
                print("WARNING: KBGrounder: logical 'or' not yet implemented")
                pass

            elif self.is_logical(root.idx, 'the'):
                if debug:
                    print ("ground_semantic_tree: processing 'the' root")
                # Return the lambda assignment of the child lambda instantiation below this node if it is a singleton,
                # else return no groundings.
                if len(child_groundings[0]) == 1:
                    c, la, conf = child_groundings[0]  # 'the' takes one argument which must be lambda-headed
                    if c:  # if the assignment created a True statement, the 'the' condition is satisfied
                        singleton = copy.deepcopy(root)
                        singleton.idx = la[0]  # change 'the' into the instantiation
                        singleton.type = self.parser.ontology.entries[la[0]]
                        singleton.children = None
                        groundings.append((singleton, [], conf))  # ignore lambda assignments contained below this level

            elif self.is_logical(root.idx, 'a'):
                if debug:
                    print ("ground_semantic_tree: processing 'a' root")
                # Return the lambda assignments of the child lambda instantiation below this node
                for c, la, conf in child_groundings[0]:  # 'a' takes one argument which must be lambda-headed
                    if c:  # if the assignment created a True statement, the 'a' condition is satisfied
                        inst = copy.deepcopy(root)
                        inst.idx = la[0]  # change 'a' into the instantiation
                        inst.type = self.parser.ontology.entries[la[0]]
                        inst.children = None
                        groundings.append((inst, [], conf))  # ignore lambda assignments contained below this level

            # KB predicates (any predicate whose eventual return type is 't')
            elif root.return_type == self.parser.ontology.types.index('t'):
                if debug:
                    print ("ground_semantic_tree: processing query root")

                # Assemble queries from the predicate and its children.
                queries = [[self.parser.ontology.preds[root.idx]]]  # every child combination will extend this query set
                for cidx in range(len(child_groundings)):
                    queries_ext = []
                    for gidx in range(len(child_groundings[cidx])):
                        args = [self.parser.ontology.preds[child_groundings[cidx][gidx][0].idx]]

                        # Verify that all object oidx args are part of the active_test_set.
                        active_test_query = True
                        for arg in args:
                            if 'oidx' in arg and int(arg.split('_')[1]) not in self.active_test_set:
                                active_test_query = False
                                break

                        if active_test_query:
                            for q in queries:
                                queries_ext.append(q + args)
                    queries = queries_ext[:]

                # Run queries to get groundings.
                # Ignore lambda assignments contained below this level.
                for q in queries:
                    if debug:
                        print("ground_semantic_tree: running kb query q=" + str(q))
                    pos_conf, neg_conf = self.kb.query(tuple(q))
                    if pos_conf > 0:
                        groundings.append((True, [], pos_conf))
                    if neg_conf > 0:
                        groundings.append((False, [], neg_conf))

            # Else, root and grounded children can be passed up as they are (e.g. actions).
            else:
                if debug:
                        print ("ground_semantic_tree: no need to ground current root further; " +
                               "forming groundings to return from " + self.parser.print_parse(root))

                build_returns = [copy.deepcopy(root)]
                build_conf = [1.0]
                for cidx in range(len(child_groundings)):
                    inst_children = []
                    inst_conf = []
                    for gidx in range(len(child_groundings[cidx])):
                        for br_idx in range(len(build_returns)):
                            inst_c = copy.deepcopy(build_returns[br_idx])
                            inst_c.children[cidx] = child_groundings[cidx][gidx][0]
                            inst_children.append(inst_c)
                            inst_conf.append(build_conf[br_idx] * child_groundings[cidx][gidx][2])
                    build_returns = inst_children
                    build_conf = inst_conf
                for br_idx in range(len(build_returns)):
                    groundings.append((build_returns[br_idx], [], build_conf[br_idx]))

        # If the head of the tree is a leaf, just return the singleton of this root.
        else:
            groundings.append((root, [], 1.0))

        if debug:
            print ("ground_semantic_tree: groundings for root " + self.parser.print_parse(root) + ": " +
                   "\n\t" + "\n\t".join([" ".join([str(t) if type(t) is bool else self.parser.print_parse(t),
                                                   str(l), str(c)])
                                        for t, l, c in groundings]))
        return groundings

    # Given a tree, a lambda name, and an assignment, instantiate all lambdas of that name to the assignment.
    def instantiate_lambda(self, root, name, assignment):
        debug = False
        if debug:
            print ("instantiate_lambda called for " + self.parser.print_parse(root) + ", " + str(name) +
                   ", " + str(assignment))

        to_process = [root]
        while len(to_process) > 0:
            n = to_process.pop()
            if n.is_lambda and n.lambda_name == name:
                n.is_lambda = False
                n.lambda_name = None
                n.idx = assignment
            if n.children is not None:
                to_process.extend(n.children)

        if debug:
            print("instantiate_lambda: produced " + self.parser.print_parse(root))

    # returns all possible ontological assignments to lambdas of a given type
    def assignments_for_type(self, t):
        return [idx for idx in range(len(self.parser.ontology.preds))
                if (self.parser.ontology.entries[idx] == t and
                    (self.parser.ontology.types[t] != 'i'
                     or int(self.parser.ontology.preds[idx].split('_')[1]) in self.active_test_set))]

    # determine whether a predicate is logical
    def is_logical(self, idx, logical_root):
        pred = self.parser.ontology.preds[idx]
        if pred == logical_root:
            return True
        elif '_' in pred and logical_root in pred.split('_'):  # .e.g a_i, a_l for instantiations of a
            return True
        return False

    # get all the commutative logicals from the parser ontology
    def get_commutative_logicals(self, logical_roots):
        cl_idxs = []
        for idx in range(len(self.parser.ontology.preds)):
            pred = self.parser.ontology.preds[idx]
            if pred in logical_roots:
                cl_idxs.append(idx)
            elif '_' in pred:
                for ps in pred.split('_'):
                    if ps in logical_roots:
                        cl_idxs.append(idx)
                        break
        return cl_idxs
