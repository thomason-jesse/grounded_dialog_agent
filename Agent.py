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
        self.action_args = {'walk': {'patient': 'l'},
                            'bring': {'patient': 'i', 'recipient': 'p'}}  # expected argument types per action

        self.action_belief_state = None  # maintained during action dialogs to track action, patient, recipient

    # Start a new action dialog from utterance u given by a user.
    # Clarifies the arguments of u until the action is confirmed by the user.
    def start_action_dialog(self, u):
        debug = True

        # Start with a count of 1.0 on each role being empty (of which only recipient can remain empty in the end).
        # As more open-ended and yes/no utterances are parsed, these counts will be updated to reflect the roles
        # we are trying to fill. Action beliefs are sampled from probability distributions induced from these counts.
        self.action_belief_state = {'action': {a: 1.0 for a in self.actions},
                                    'patient': {p: 1.0 for p in self.parser.ontology.preds
                                                if (self.parser.ontology.entries[self.parser.ontology.preds.index(p)] ==
                                                    self.parser.ontology.types.index(
                                                        self.action_args['walk']['patient']) or
                                                    self.parser.ontology.entries[self.parser.ontology.preds.index(p)] ==
                                                    self.parser.ontology.types.index(
                                                        self.action_args['bring']['patient']))},
                                    'recipient': {r: 1.0 for r in self.parser.ontology.preds
                                                  if self.parser.ontology.entries[self.parser.ontology.preds.index(r)]
                                                  == self.parser.ontology.types.index(
                                                      self.action_args['bring']['recipient'])}}
        for r in self.roles:
            self.action_belief_state[r][None] = 1.0
        if debug:
            print ("start_action_dialog starting with u '" + str(u) + "' and action belief state: "
                   + str(self.action_belief_state))

        # Run the parser and grounder on the utterance
        gp = self.parse_and_ground_utterance(u)

        # Update the belief state based on the utterance.
        self.update_action_belief_from_parse(gp, self.roles)

        # Ask a follow up question based on the new belief state.
        # This continues until an action is chosen.
        action_confirmed = {r: None for r in self.roles}
        while (action_confirmed['action'] is None or action_confirmed['patient'] is None or
                (action_confirmed['action'] == 'bring' and action_confirmed['recipient'] is None)):

            # Sample a chosen action from the current belief counts.
            action_chosen = self.sample_action_from_belief(action_confirmed)

            # Determine what question to ask based on missing arguments in chosen action.
            q, role_asked, roles_conf = self.get_question_from_sampled_action(action_chosen,
                                                                              self.threshold_to_accept_role)

            # Ask question and get user response.
            self.io.say_to_user(q)
            ur = self.io.get_from_user()

            # Update action belief based on user response.
            gpr = self.parse_and_ground_utterance(ur)
            if action_chosen[role_asked][0] is None:  # asked an open-ended question for a particular role
                self.update_action_belief_from_parse(gpr, [role_asked])
            else:  # asked a yes/no question confirming one or more roles
                if debug:
                    print "start_action_dialog: confirmation response parse " + self.parser.print_parse(gpr.node)
                if gpr.node.type == self.parser.ontology.types.index('c'):
                    if gpr.node.idx == self.parser.ontology.preds.index('yes'):
                        action_confirmed[role_asked] = action_chosen[role_asked][0]
                        for r in roles_conf:
                            action_confirmed[r] = action_chosen[r][0]
                    elif gpr.node.idx == self.parser.ontology.preds.index('no'):
                        self.action_belief_state[role_asked][action_chosen[role_asked][0]] -= 1.0
                        for r in roles_conf:
                            self.action_belief_state[r][action_chosen[r][0]] -= 1.0
                else:
                    # TODO: could add a loop here to force expected response type; create feedback for
                    # TODO: getting synonyms for yes/no maybe
                    print "WARNING: user did not respond to confirmation with yes/no"

        # Perform the chosen action.
        self.io.perform_action(action_confirmed['action'], action_confirmed['patient'],
                               action_confirmed['recipient'])

    # Parse and ground a given utterance.
    def parse_and_ground_utterance(self, u):
        debug = True

        # TODO: do probabilistic updates by normalizing the parser outputs in a beam instead of only considering top-1
        parse_generator = self.parser.most_likely_cky_parse(u, reranker_beam=self.parse_beam)
        p, _, _, _ = next(parse_generator)
        if debug:
            print "parse_and_ground_utterance: parsed '" + u + "' to " + self.parser.print_parse(p.node)
        g = self.grounder.ground_semantic_node(p.node)
        if debug:
            print "parse_and_ground_utterance: groundings " + g
        return g


    # Given a parse and a list of the roles felicitous in the dialog to update, update those roles' distributions
    def update_action_belief_from_parse(self, p, roles, count=1.0):
        debug = True
        if debug:
            print ("update_action_belief_from_parse called with p " + self.parser.print_parse(p.node) +
                   " and roles " + str(roles))

        # Crawl parse for recognized actions.
        if 'action' in roles:
            action_trees = self.get_parse_subtrees(p.node, self.actions)
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
                            if self.parser.ontology.types[cn.type] == self.action_args[a][r]:
                                c = self.parser.ontology.preds[cn.idx]
                                if c not in self.action_belief_state[r]:
                                    self.action_belief_state[r][c] = 0
                                self.action_belief_state[r][c] += count / len(action_trees)
                                if debug:
                                    print "update_action_belief_from_parse: adding count to " + r + " " + c

        # Else, just add counts as appropriate based on roles asked based on a trace of the whole tree.
        else:
            to_traverse = [p.node]
            to_increment = []
            while len(to_traverse) > 0:
                for r in roles:
                    cn = to_traverse.pop()
                    print "role " + r + " action types expected " + str([t for a in self.actions if r in self.action_args[a] for t in self.action_args[a][r]]) + " type examining " + str(self.parser.ontology.types[cn.type])  # DEBUG
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
    def sample_action_from_belief(self, current_confirmed):

        chosen = {r: (None, 0) if current_confirmed[r] is None else (current_confirmed[r], 1.0)
                  for r in self.roles}
        for r in [_r for _r in self.roles if current_confirmed[_r] is None]:

            mass = sum([self.action_belief_state[r][entry] for entry in self.action_belief_state[r]])
            if mass > 0:
                dist = [self.action_belief_state[r][entry] / mass for entry in self.action_belief_state[r]]
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

        relevant_roles = self.roles[:]
        confidences = {r: sampled_action[r][1] for r in self.roles}
        s_conf = sorted(confidences.items(), key=operator.itemgetter(1))
        if debug:
            print "get_question_from_sampled_action: s_conf " + str(s_conf)

        # Determine which args to include as already understood in question and which arg to focus on.
        roles_to_include = [r for r in relevant_roles if sampled_action[r][1] >= include_threshold]
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
