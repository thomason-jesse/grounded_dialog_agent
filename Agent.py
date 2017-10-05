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

        self.action_belief_state = {r: {} for r in self.roles}

        # Run the parser on the utterance
        # TODO: do probabilistic updates by normalizing the parser outputs in a beam instead of only considering top-1
        parse_generator = self.parser.most_likely_cky_parse(u, reranker_beam=self.parse_beam)
        p, _, _, _ = next(parse_generator)

        # Update the belief state based on the utterance.
        self.update_action_belief_from_parse(p, self.roles)

        # Ask a follow up question based on the new belief state.
        # This continues until an action is chosen.
        action_confirmed = False
        action_chosen = None
        while not action_confirmed:

            # Sample a chosen action from the current belief counts.
            action_chosen = self.sample_action_from_belief()

            # Determine what question to ask based on missing arguments in chosen action.
            q, role_asked, roles_conf = self.get_question_from_sampled_action(action_chosen,
                                                                              self.threshold_to_accept_role)

            # Ask question and get user response.
            self.io.say_to_user(q)
            ur = self.io.get_from_user()

            # Update action belief based on user response, the role asked about, and the roles included.
            self.update_action_belief_from_response(ur, role_asked, roles_conf)

    # Given a parse and a list of the roles felicitous in the dialog to update, update those roles' distributions
    def update_action_belief_from_parse(self, p, roles):

        # Crawl parse for recognized actions.
        if 'action' in roles:
            action_trees = self.get_parse_subtrees(p, self.actions)
            for at in action_trees:
                a = self.parser.ontology.preds[at.idx]
                if a not in self.action_belief_state['action']:
                    self.action_belief_state['action'][a] = 0
                # TODO: these updates could be scaled by a normalized parse confidence
                self.action_belief_state['action'][a] += 1.0 / len(at)

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
                                self.action_belief_state[r][c] += 1.0 / len(at)

    # Given a parse and a list of predicates, return the subtrees in the parse rooted at those predicates.
    # If a subtree is rooted beneath one of the specified predicates, it will not be returned (top-level only).
    def get_parse_subtrees(self, root, preds):
        trees_found = []
        if root.idx in preds:
            trees_found.append(root)
        elif root.children is not None:
            for c in root.children:
                trees_found.extend(self.get_parse_subtrees(c, preds))
        return trees_found

    # Sample a discrete action from the current belief counts.
    # Each argument of the discrete action is a tuple of (argument, confidence) for confidence in [0, 1].
    def sample_action_from_belief(self):

        chosen = {r: (None, 0) for r in self.roles}
        for r in self.roles:

            mass = sum([self.action_belief_state[r][entry] for entry in self.action_belief_state[r]])
            if mass > 0:
                dist = [self.action_belief_state[r][entry] / mass for entry in self.action_belief_state[r]]
                chosen[r] = np.random.choice([(self.action_belief_state[r].keys()[idx], dist[idx])
                                              for idx in range(len(self.action_belief_state[r].keys()))],
                                             1, p=dist)

        return chosen

    # Return a string question based on a discrete sampled action.
    def get_question_from_sampled_action(self, sampled_action, include_threshold):

        relevant_roles = self.roles[:]
        confidences = {r: sampled_action[r][1] for r in self.roles}
        s_conf = sorted(confidences.items(), key=operator.itemgetter(1))

        # If not asking about the action, re-sort based on felicitous arguments.
        if s_conf[0][0] != 'action':
            relevant_roles = self.action_args[sampled_action['action']].keys()
            confidences = {r: sampled_action[r][1] for r in relevant_roles}
            s_conf = sorted(confidences.items(), key=operator.itemgetter(1))

        # Determine which args to include as already understood in question and which arg to focus on.
        roles_to_include = [r for r in relevant_roles if sampled_action[r][1] >= include_threshold]
        least_conf_role = s_conf[0][0]
        if s_conf[0][0] == s_conf[0][1] == s_conf[0][2] == 0.0:  # no confidence
            least_conf_role = None

        # Ask a question.
        if roles_to_include == self.roles:  # all roles are above threshold, so perform.
            if sampled_action['action'][0] == 'walk':
                q = "I will go to " + sampled_action['patient'][0] + "."
            else:
                q = ("I will deliver " + sampled_action['patient'][0] + " to " +
                     sampled_action['recipient'][0] + ".")
        elif least_conf_role == 'action':  # ask for action confirmation
            if sampled_action['action'][0] == 'walk':
                if 'patient' in roles_to_include:
                    q = "You want me to go to " + sampled_action['patient'][0] + "?"
                else:
                    q = "You want me to go somewhere?"
            else:
                if 'patient' in roles_to_include:
                    q = "You want me to deliver " + sampled_action['patient'][0] + " to someone?"
                elif 'recipient' in roles_to_include:
                    q = "You want me to deliver something to " + sampled_action['recipient'][0] + "?"
                else:
                    q = "You want me to deliver something for someone?"
        elif least_conf_role == 'patient':  # ask for patient confirmation
            if 'action' in roles_to_include:
                if sampled_action['action'][0] == 'walk':
                    q = "You want me to walk to " + sampled_action['patient'][0] + "?"
                else:
                    q = "You want me to deliver " + sampled_action['patient'][0] + " to someone?"
            else:
                q = "You want me to do something involving " + sampled_action['patient'][0] + "?"
        elif least_conf_role == 'recipient':  # ask for recipient confirmation
            if 'action' in roles_to_include:
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
