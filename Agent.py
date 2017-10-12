#!/usr/bin/env python
__author__ = 'jesse'

import numpy as np
import operator


class Agent:

    # Takes an instantiated, trained parser, a knowledge base grounder, and an input/output instance.
    def __init__(self, parser, grounder, io):
        self.parser = parser
        self.grounder = grounder
        self.io = io

        # hyperparameters
        self.parse_beam = 1
        self.threshold_to_accept_role = 0.9

        # static information about expected actions and their arguments
        self.roles = ['action', 'patient', 'recipient']
        self.actions = ['walk', 'bring']
        self.action_args = {'walk': {'patient': ['l']},
                            'bring': {'patient': ['i'], 'recipient': ['l']}}  # expected argument types per action

        self.action_belief_state = None  # maintained during action dialogs to track action, patient, recipient
        self.induced_utterance_grounding_pairs = []  # pairs of [utterance, SemanticNode] induced from conversations

    # Start a new action dialog from utterance u given by a user.
    # Clarifies the arguments of u until the action is confirmed by the user.
    def start_action_dialog(self, u):
        debug = True

        # Start with a count of 1.0 on each role being empty (of which only recipient can remain empty in the end).
        # As more open-ended and yes/no utterances are parsed, these counts will be updated to reflect the roles
        # we are trying to fill. Action beliefs are sampled from probability distributions induced from these counts.
        self.action_belief_state = {'action': {a: 1.0 for a in self.actions},
                                    'patient': {p: 1.0 for p in self.parser.ontology.preds
                                                if (self.parser.ontology.types[self.parser.ontology.entries[
                                                        self.parser.ontology.preds.index(p)]] in
                                                    self.action_args['walk']['patient'] or
                                                    self.parser.ontology.types[self.parser.ontology.entries[
                                                        self.parser.ontology.preds.index(p)]] in
                                                    self.action_args['bring']['patient'])},
                                    'recipient': {r: 1.0 for r in self.parser.ontology.preds
                                                  if self.parser.ontology.types[self.parser.ontology.entries[
                                                      self.parser.ontology.preds.index(r)]] in
                                                  self.action_args['bring']['recipient']}}
        for r in self.roles:
            self.action_belief_state[r][None] = 1.0
        if debug:
            print ("start_action_dialog starting with u '" + str(u) + "' and action belief state: "
                   + str(self.action_belief_state))

        user_utterances_by_role = {r: [] for r in self.roles + ['all']}
        user_utterances_by_role['all'].append(u)

        # Run the parser and grounder on the utterance
        gps = self.parse_and_ground_utterance(u)

        # Update the belief state based on the utterance.
        for gp, conf in gps:
            self.update_action_belief_from_grounding(gp, self.roles, count=conf / len(gps))

        # Ask a follow up question based on the new belief state.
        # This continues until an action is chosen.
        action_confirmed = {r: None for r in self.roles}
        while (action_confirmed['action'] is None or action_confirmed['patient'] is None or
                (action_confirmed['action'] == 'bring' and action_confirmed['recipient'] is None)):

            # Sample a chosen action from the current belief counts.
            # If arg_max, gets current highest-confidence belief. Else, creates confidence distribution and samples.
            action_chosen = self.sample_action_from_belief(action_confirmed, arg_max=True)

            # Determine what question to ask based on missing arguments in chosen action.
            q, role_asked, roles_conf = self.get_question_from_sampled_action(action_chosen,
                                                                              self.threshold_to_accept_role)

            # Ask question and get user response.
            self.io.say_to_user(q)
            ur = self.io.get_from_user()

            # Update action belief based on user response.
            gprs = self.parse_and_ground_utterance(ur)
            if role_asked is None:  # asked to repeat whole thing
                user_utterances_by_role['all'].append(ur)
                for gpr, conf in gprs:
                    self.update_action_belief_from_grounding(gpr, self.roles, count=conf / len(gprs))
            elif action_chosen[role_asked][0] is None:  # asked an open-ended question for a particular role
                user_utterances_by_role[role_asked].append(ur)
                for gpr, conf in gprs:
                    self.update_action_belief_from_grounding(gpr, [role_asked], count=conf / len(gprs))
            else:  # asked a yes/no question confirming one or more roles
                for gpr, conf in gprs:
                    if debug:
                        print "start_action_dialog: confirmation response parse " + self.parser.print_parse(gpr)
                    if gpr.type == self.parser.ontology.types.index('c'):
                        if gpr.idx == self.parser.ontology.preds.index('yes'):
                            action_confirmed[role_asked] = action_chosen[role_asked][0]
                            for r in roles_conf:
                                action_confirmed[r] = action_chosen[r][0]
                        elif gpr.idx == self.parser.ontology.preds.index('no'):
                            for r in roles_conf:
                                self.action_belief_state[r][action_chosen[r][0]] -= \
                                    (conf / len(gprs)) / float(len(roles_conf))
                                if debug:
                                    print ("start_action_dialog: subtracting count from " + r + " " +
                                           action_chosen[r][0])
                    else:
                        # TODO: could add a loop here to force expected response type; create feedback for
                        # TODO: getting synonyms for yes/no maybe
                        print "WARNING: grounding for confirmation did not produce yes/no"

            if debug:
                print "start_action_dialog: updated action belief state: " + str(self.action_belief_state)

        # Induce utterance/grounding pairs from this conversation.
        new_i_pairs = self.induce_utterance_grounding_pairs_from_conversation(user_utterances_by_role,
                                                                              action_confirmed)
        self.induced_utterance_grounding_pairs.extend(new_i_pairs)

        # Perform the chosen action.
        self.io.perform_action(action_confirmed['action'], action_confirmed['patient'],
                               action_confirmed['recipient'])

    # Given a dictionary of roles to utterances and another of roles to confirmed predicates, build
    # SemanticNodes corresponding to those predicates and to the whole command to match up with entries
    # in the utterance dictionary.
    def induce_utterance_grounding_pairs_from_conversation(self, us, rs):
        debug = True

        pairs = []
        if 'all' in us:  # need to build SemanticNode representing all roles
            sem_str = rs['action']
            if rs['action'] == 'walk':
                sem_str += '(' + rs['patient'] + ')'
            else:  # i.e. 'bring'
                sem_str += '(' + rs['patient'] + ',' + rs['recipient'] + ')'
            cat_idx = self.parser.lexicon.read_category_from_str('M')  # a command
            grounded_form = self.parser.lexicon.read_semantic_form_from_str(sem_str, cat_idx,
                                                                            None, [], False)
            for u in us['all']:
                pairs.append([u, grounded_form])
            if debug:
                print ("induce_utterance_grounding_pairs_from_conversation: adding 'all' pairs for gr form " +
                       self.parser.print_parse(grounded_form) + " for utterances: " + ' ; '.join(us['all']))

        for r in [_r for _r in self.roles if _r in us and rs[_r] is not None]:
            if r == 'action':
                # TODO: Seems like we should do something here but it's actually not clear to me what a grounding
                # TODO: for an action word by itself looks like. The syntax around them, like, matters.
                # TODO: These might have to be learned primarily through the overall restatement, in which case
                # TODO: we should disallow it as the role_asked and default to full restate when the least
                # TODO: confident role comes out as 'action'.
                pass

            else:
                cat_idx = self.parser.lexicon.read_category_from_str('NP')  # patients and recipients always NP alone
                grounded_form = self.parser.lexicon.read_semantic_form_from_str(rs[r], cat_idx,
                                                                                None, [], False)

                for u in us[r]:
                    pairs.append([u, grounded_form])
                if debug and len(us[r]) > 0:
                    print ("induce_utterance_grounding_pairs_from_conversation: adding '" + r + "' pairs for gr form " +
                           self.parser.print_parse(grounded_form) + " for utterances: " + ' ; '.join(us[r]))

        return pairs

    # Parse and ground a given utterance.
    def parse_and_ground_utterance(self, u):
        debug = True

        # TODO: do probabilistic updates by normalizing the parser outputs in a beam instead of only considering top-1
        # TODO: confidence could be propagated through the confidence values returned by the grounder, such that
        # TODO: this function returns tuples of (grounded parse, parser conf * grounder conf)
        parse_generator = self.parser.most_likely_cky_parse(u, reranker_beam=self.parse_beam)
        p, _, _, _ = next(parse_generator)
        if p is not None:
            if debug:
                print "parse_and_ground_utterance: parsed '" + u + "' to " + self.parser.print_parse(p.node)

            # Get semantic trees with hanging lambdas instantiated.
            gs = self.grounder.ground_semantic_tree(p.node)

            # normalize grounding confidences such that they sum to one and return pairs of grounding, conf
            gn = self.sort_groundings_by_conf(gs)

            if debug:
                print ("parse_and_ground_utterance: resulting groundings with normalized confidences " +
                       "\n\t" + "\n\t".join([" ".join([str(t) if type(t) is bool else self.parser.print_parse(t),
                                                       str(c)])
                                            for t, c in gn]))
        else:
            if debug:
                print "parse_and_ground_utterance: could not generate a parse for the utterance"
            gn = []

        return gn

    # Given a set of groundings, return them and their confidences in sorted order.
    def sort_groundings_by_conf(self, gs):
        s = sum([c for _, _, c in gs])
        gn = [(t, c / s if s > 0 else c / float(len(gs))) for t, _, c in gs]
        return sorted(gn, key=lambda x: x[1], reverse=True)

    # Given a parse and a list of the roles felicitous in the dialog to update, update those roles' distributions
    def update_action_belief_from_grounding(self, g, roles, count=1.0):
        debug = True
        if debug:
            print ("update_action_belief_from_grounding called with g " + self.parser.print_parse(g) +
                   " and roles " + str(roles))

        # Crawl parse for recognized actions.
        if 'action' in roles:
            action_trees = self.get_parse_subtrees(g, self.actions)
            for at in action_trees:
                a = self.parser.ontology.preds[at.idx]
                if a not in self.action_belief_state['action']:
                    self.action_belief_state['action'][a] = 0
                # TODO: these updates could be scaled by a normalized parse confidence
                self.action_belief_state['action'][a] += count / float(len(action_trees))
                if debug:
                    print "update_action_belief_from_parse: adding count to action " + a

                # Update patient and recipient, if present, with action tree args.
                # These disregard argument order in favor of finding matching argument types.
                # This gives us more robustness to bad parses with incorrectly ordered args or incomplete args.
                # However, if we eventually have commands that take two args of the same type, we will
                # have to introduce explicit ordering constraints here for those.
                for r in ['patient', 'recipient']:
                    if r in roles and at.children is not None:
                        for cn in at.children:
                            if (r in self.action_args[a] and
                                    self.parser.ontology.types[cn.type] in self.action_args[a][r]):
                                c = self.parser.ontology.preds[cn.idx]
                                if c not in self.action_belief_state[r]:
                                    self.action_belief_state[r][c] = 0
                                self.action_belief_state[r][c] += count / len(action_trees)
                                if debug:
                                    print "update_action_belief_from_parse: adding count to " + r + " " + c

        # Else, just add counts as appropriate based on roles asked based on a trace of the whole tree.
        else:
            to_traverse = [g]
            to_increment = []
            while len(to_traverse) > 0:
                for r in roles:
                    cn = to_traverse.pop()
                    if self.parser.ontology.types[cn.type] in [t for a in self.actions
                                                               if r in self.action_args[a]
                                                               for t in self.action_args[a][r]]:
                        if not cn.is_lambda:  # otherwise utterance isn't grounded
                            c = self.parser.ontology.preds[cn.idx]
                            if c not in self.action_belief_state[r]:
                                self.action_belief_state[r][c] = 0
                            to_increment.append((r, c))
                    if cn.children is not None:
                        to_traverse.extend(cn.children)
            for r, c in to_increment:
                self.action_belief_state[r][c] += count / len(to_increment)
                if debug:
                    print "update_action_belief_from_parse: adding count to " + r + " " + c

    # Given a parse and a list of predicates, return the subtrees in the parse rooted at those predicates.
    # If a subtree is rooted beneath one of the specified predicates, it will not be returned (top-level only).
    def get_parse_subtrees(self, root, preds):
        debug = True
        if debug:
            print "get_parse_subtrees called for root " + self.parser.print_parse(root) + " and preds " + str(preds)

        trees_found = []
        pred_idxs = [self.parser.ontology.preds.index(p) for p in preds]
        if root.idx in pred_idxs:
            trees_found.append(root)
        elif root.children is not None:
            for c in root.children:
                trees_found.extend(self.get_parse_subtrees(c, preds))
        if debug:
            print "get_parse_subtrees: found trees " + str(trees_found)  # DEBUG
        return trees_found

    # Sample a discrete action from the current belief counts.
    # Each argument of the discrete action is a tuple of (argument, confidence) for confidence in [0, 1].
    def sample_action_from_belief(self, current_confirmed, arg_max=False):

        chosen = {r: (None, 0) if current_confirmed[r] is None else (current_confirmed[r], 1.0)
                  for r in self.roles}
        for r in [_r for _r in self.roles if current_confirmed[_r] is None]:

            min_count = min([self.action_belief_state[r][entry] for entry in self.action_belief_state[r]])
            mass = sum([self.action_belief_state[r][entry] - min_count for entry in self.action_belief_state[r]])
            if mass > 0:
                dist = [(self.action_belief_state[r][entry] - min_count) / mass
                        for entry in self.action_belief_state[r]]
                if arg_max:
                    max_idxs = [idx for idx in range(len(dist)) if dist[idx] == max(dist)]
                    c = np.random.choice([self.action_belief_state[r].keys()[idx] for idx in max_idxs], 1)
                else:
                    c = np.random.choice([self.action_belief_state[r].keys()[idx]
                                          for idx in range(len(self.action_belief_state[r].keys()))],
                                         1, p=dist)
                chosen[r] = (c[0], dist[self.action_belief_state[r].keys().index(c)])

        return chosen

    # Return a string question based on a discrete sampled action.
    def get_question_from_sampled_action(self, sampled_action, include_threshold):
        debug = True
        if debug:
            print "get_question_from_sampled_action called with " + str(sampled_action) + ", " + str(include_threshold)

        roles_to_include = [r for r in self.roles if sampled_action[r][1] >= include_threshold]
        if 'action' in roles_to_include:
            relevant_roles = ['action'] + [r for r in (self.action_args[sampled_action['action'][0]].keys()
                                           if sampled_action['action'][0] is not None else ['patient', 'recipient'])]
        else:
            relevant_roles = self.roles[:]
        confidences = {r: sampled_action[r][1] for r in relevant_roles}
        s_conf = sorted(confidences.items(), key=operator.itemgetter(1))
        if debug:
            print "get_question_from_sampled_action: s_conf " + str(s_conf)

        # Determine which args to include as already understood in question and which arg to focus on.
        least_conf_role = s_conf[0][0]
        if max([conf for _, conf in s_conf]) == 0.0:  # no confidence
            least_conf_role = None
        if debug:
            print ("get_question_from_sampled_action: roles_to_include " + str(roles_to_include) +
                   " with least_conf_role " + str(least_conf_role))

        # Ask a question.
        if roles_to_include == self.roles:  # all roles are above threshold, so perform.
            if sampled_action['action'][0] == 'walk':
                q = "You want me to go to " + sampled_action['patient'][0] + "?"
            else:
                q = ("You want me to deliver " + sampled_action['patient'][0] + " to " +
                     sampled_action['recipient'][0] + "?")
        elif least_conf_role == 'action':  # ask for action confirmation
            if sampled_action['action'][0] is None:
                if 'patient' in roles_to_include:
                    q = "What should I do involving " + sampled_action['patient'][0] + "?"
                elif 'recipient' in roles_to_include:
                    q = "What should I do involving " + sampled_action['recipient'][0] + "?"
                else:
                    q = "What kind of action should I perform?"
            elif sampled_action['action'][0] == 'walk':
                if 'patient' in roles_to_include:
                    q = "You want me to go to " + sampled_action['patient'][0] + "?"
                else:
                    q = "You want me to go somewhere?"
            else:  # i.e. bring
                if 'patient' in roles_to_include:
                    if 'recipient' in roles_to_include:
                        q = ("You want me to deliver " + sampled_action['patient'][0] + " to "
                             + sampled_action['recipient'][0] + "?")
                    else:
                        q = "You want me to deliver " + sampled_action['patient'][0] + " to someone?"
                elif 'recipient' in roles_to_include:
                    q = "You want me to deliver something to " + sampled_action['recipient'][0] + "?"
                else:
                    q = "You want me to deliver something for someone?"
        elif least_conf_role == 'patient':  # ask for patient confirmation
            if sampled_action['patient'][0] is None:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'walk':
                        q = "Where should I go?"
                    elif 'recipient' in roles_to_include:
                        q = "What should I deliver to " + sampled_action['recipient'][0] + "?"
                    else:  # i.e. bring with no recipient
                        q = "What should I find to deliver?"
                else:
                    if 'recipient' in roles_to_include:
                        q = ("What else is involved in what I should do besides " +
                             sampled_action['recipient'][0] + "?")
                    else:
                        q = "What is involved in what I should do?"
            else:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'walk':
                        q = "You want me to walk to " + sampled_action['patient'][0] + "?"
                    elif 'recipient' in roles_to_include:
                        q = ("You want me to deliver " + sampled_action['patient'][0] + " to " +
                             sampled_action['recipient'][0] + "?")
                    else:
                        q = "You want me to deliver " + sampled_action['patient'][0] + " to someone?"
                else:
                    if 'recipient' in roles_to_include:
                        q = ("You want me to do something involving " + sampled_action['patient'][0] +
                             " for " + sampled_action['recipient'][0] + "?")
                    else:
                        q = "You want me to do something involving " + sampled_action['patient'][0] + "?"
        elif least_conf_role == 'recipient':  # ask for recipient confirmation
            if sampled_action['recipient'][0] is None:
                if 'action' in roles_to_include:
                    if sampled_action['action'][0] == 'walk':
                        raise ValueError("ERROR: get_question_from_sampled_action got a sampled action " +
                                         "with empty recipient ask in spite of action being walk")
                    elif 'patient' in roles_to_include:
                        q = "To whom should I deliver " + sampled_action['patient'][0] + "?"
                    else:  # i.e. bring with no recipient
                        q = "Who should receive what I deliver?"
                else:
                    if 'patient' in roles_to_include:
                        q = "Who is involved in what I should do with " + sampled_action['patient'][0] + "?"
                    else:
                        q = "Who is involved in what I should do?"
            else:
                if 'action' in roles_to_include:
                    if 'patient' in roles_to_include:
                        q = ("You want me to deliver " + sampled_action['patient'][0] + " to " +
                             sampled_action['recipient'][0] + "?")
                    else:
                        q = "You want me to deliver something to " + sampled_action['recipient'][0] + "?"
                elif 'patient' in roles_to_include:
                    q = ("You want me to do something with " + sampled_action['patient'][0] + " for " +
                         sampled_action['recipient'][0] + "?")
                else:
                    q = "You want me to do something for " + sampled_action['recipient'][0] + "?"
        else:  # least_conf_role is None, i.e. no confidence in any arg, so ask for full restatement
            q = "Could you rephrase your request?"

        # Return the question and the roles included in it.
        # If the user affirms, all roles included in the question should have confidence boosted to 1.0
        # If the user denies, all roles included in the question should have their counts subtracted.
        return q, least_conf_role, roles_to_include

    # take in data set d=(x,g) for x strings and g correct groundings and calculate training pairs
    # training pairs in t are of form (x, y_chosen, y_correct, chosen_lex_entries, correct_lex_entries)
    # k determines how many parses to get for re-ranking
    # beam determines how many cky_trees to look through before giving up on a given input
    # TODO: this is almost identical to the cky parser training function, and could probably be done more
    # TODO: smartly by passing a function to that function to be used for the comparator that, instead
    # TODO: of comparing parses, grounds the generated parse and compares the groundings like this does.
    def get_parser_training_pairs_from_grounding_data(self, d, verbose, reranker_beam=1):
        t = []
        num_trainable = 0
        num_matches = 0
        num_fails = 0
        num_genlex_only = 0
        for [x, g] in d:
            correct_parse = None
            correct_new_lexicon_entries = []
            # TODO: providing some possible known roots through some kind of reverse parsing might help here
            cky_parse_generator = self.parser.most_likely_cky_parse(x, reranker_beam=reranker_beam,
                                                                    debug=False)
            chosen_parse, chosen_score, chosen_new_lexicon_entries, chosen_skipped_surface_forms = \
                next(cky_parse_generator)
            current_parse = chosen_parse
            correct_score = chosen_score
            current_new_lexicon_entries = chosen_new_lexicon_entries
            current_skipped_surface_forms = chosen_skipped_surface_forms
            match = False
            first = True
            if chosen_parse is None:
                if verbose >= 2:
                    print "WARNING: could not find valid parse for '" + x + "' during training"
                num_fails += 1
                continue
            while correct_parse is None and current_parse is not None:
                gs = self.grounder.ground_semantic_tree(current_parse.node)
                gn = self.sort_groundings_by_conf(gs)
                gz, _ = gn[0]  # top confidence grounding, which may be True/False
                if ((type(gz) is bool and gz == g) or
                        (type(gz) is not bool and g.equal_allowing_commutativity(gz, self.parser.ontology))):
                    correct_parse = current_parse
                    correct_new_lexicon_entries = current_new_lexicon_entries
                    correct_skipped_surface_forms = current_skipped_surface_forms
                    if first:
                        match = True
                        num_matches += 1
                    else:
                        num_trainable += 1
                    break
                first = False
                current_parse, correct_score, current_new_lexicon_entries, current_skipped_surface_forms = \
                    next(cky_parse_generator)
            if correct_parse is None:
                if verbose >= 2:
                    print "WARNING: could not find correct parse for '"+str(x)+"' during training"
                num_fails += 1
                continue
            if verbose >= 2:
                print "\tx: "+str(x)
                print "\t\tchosen_parse: "+self.parser.print_parse(chosen_parse.node, show_category=True)
                print "\t\tchosen_score: "+str(chosen_score)
                print "\t\tchosen_skips: "+str(chosen_skipped_surface_forms)
                if len(chosen_new_lexicon_entries) > 0:
                    print "\t\tchosen_new_lexicon_entries: "
                    for sf, sem in chosen_new_lexicon_entries:
                        print "\t\t\t'"+sf+"' :- "+self.parser.print_parse(sem, show_category=True)
            if not match or len(correct_new_lexicon_entries) > 0:
                if len(correct_new_lexicon_entries) > 0:
                    num_genlex_only += 1
                if verbose >= 2:
                    print "\t\ttraining example generated:"
                    print "\t\t\tcorrect_parse: "+self.parser.print_parse(correct_parse.node, show_category=True)
                    print "\t\t\tcorrect_score: "+str(correct_score)
                    print "\t\t\tcorrect_skips: " + str(correct_skipped_surface_forms)
                    if len(correct_new_lexicon_entries) > 0:
                        print "\t\t\tcorrect_new_lexicon_entries: "
                        for sf, sem in correct_new_lexicon_entries:
                            print "\t\t\t\t'"+sf+"' :- "+self.parser.print_parse(sem, show_category=True)
                    print "\t\t\tg: "+self.parser.print_parse(g, show_category=True)
                t.append([x, chosen_parse, correct_parse, chosen_new_lexicon_entries, correct_new_lexicon_entries,
                          chosen_skipped_surface_forms, correct_skipped_surface_forms])
        if verbose >= 1:
            print "\tmatched "+str(num_matches)+"/"+str(len(d))
            print "\ttrained "+str(num_trainable)+"/"+str(len(d))
            print "\tgenlex only "+str(num_genlex_only)+"/"+str(len(d))
            print "\tfailed "+str(num_fails)+"/"+str(len(d))
        return t, num_fails
