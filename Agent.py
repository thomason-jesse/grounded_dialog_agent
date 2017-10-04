#!/usr/bin/env python
__author__ = 'jesse'


class Agent:

    def __init__(self, parser, grounder):
        self.parser = parser
        self.grounder = grounder

        # hyperparameters
        self.parse_beam = 1

        self.action_belief_state = None  # maintained during action dialogs to track action, patient, recipient

    # Start a new action dialog from utterance u given by a user.
    # Clarifies the arguments of u until the action is confirmed by the user.
    def start_action_dialog(self, u):

        self.action_belief_state = {"action": {}, "patient": {}, "recipient": {}}

        # Run the parser on the utterance
        # TODO: do probabilistic updates by normalizing the parser outputs in a beam instead of only considering top-1
        parse_generator = self.parser.most_likely_cky_parse(u, reranker_beam=self.parse_beam)
        p, _, _, _ = next(parse_generator)

        # Update the belief state based on the utterance.
        self.update_action_belief(p, ["action", "patient", "recipient"])

        # TODO: start dialog based on updated belief (can use sampling strategy from IJCAI'15 or something new)

    # Given a parse and a list of the roles felicitious in the dialog to update, update those roles' distributions
    def update_action_belief(self, p, roles):

        # TODO: crawl parse and extract action, patient, recipient, updating as allows by 'roles'
        pass
