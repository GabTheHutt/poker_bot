from card_utils import Card, evaluate
from game_state import GameStateView
from player_action import PlayerAction


class Model:
    """
    Your bot: change anything in this file, and add files next to it.

    This object is what gets pickled, so load weights and data in __init__
    and keep them in plain attributes.
    """

    def __init__(self):
        self.hand = []
        self.player_id = None
        self.hands_played = 0
        self.opponent_folds = {}

    def seed(self, hand: list[Card], player_id: int):
        """
        Called once before the hand: your two hole cards and your id.

        Store them; run() is not given them again.
        """
        self.hand = hand
        self.player_id = player_id

    def _raise(self, game_state, fraction=1.0):
        if not game_state.can_raise:
            return PlayerAction.call(self.player_id)
        low, high = game_state.raise_range
        target = game_state.current_bet + max(
            game_state.last_raise,
            int(game_state.pot * fraction),
        )
        return PlayerAction.raise_to(self.player_id, min(high, max(low, target)))

    def _preflop_strength(self):
        first, second = sorted(
            (card.value for card in self.hand), reverse=True
        )
        pair = first == second
        suited = self.hand[0].suit == self.hand[1].suit
        gap = first - second
        score = 0
        if pair:
            score = 5 if first >= 12 else 4 if first >= 9 else 3
        elif first == 14:
            score = 4 if second >= 10 else 3 if second >= 8 else 2
        elif first >= 13 and second >= 10:
            score = 3
        elif first >= 11 and second >= 10:
            score = 2
        elif suited and gap <= 2 and first >= 9:
            score = 2
        elif gap <= 1 and first >= 10:
            score = 1
        return score

    def _draw_strength(self, board):
        cards = self.hand + board
        suits = {}
        for card in cards:
            suits[card.suit] = suits.get(card.suit, 0) + 1
        flush_draw = max(suits.values(), default=0) >= 4

        values = {card.value for card in cards}
        if 14 in values:
            values.add(1)
        straight_draw = any(
            len(values.intersection(range(high - 4, high + 1))) >= 4
            for high in range(5, 15)
        )
        return flush_draw, straight_draw

    def _postflop_strength(self, board):
        rank = evaluate(self.hand + board)
        made = rank[0]
        hand_ranks = {card.rank for card in self.hand}
        uses_hole = (
            self.hand[0].rank == self.hand[1].rank
            or any(card.rank in hand_ranks for card in board)
        )
        flush_draw, straight_draw = self._draw_strength(board)
        draw = flush_draw or straight_draw
        return made, uses_hole, draw

    def run(
        self, actions: list[PlayerAction], game_state: GameStateView
    ) -> PlayerAction:
        """
        Called on your turn.

        actions: everything done since your last turn this hand, oldest
            first: player moves, your own previous move included, and the
            dealer's reveal_card.
        game_state: the public state of the hand, read-only, e.g.
            game_state.call_amount, game_state.status(self.player_id),
            game_state.min_raise_to.
        """
        me = self.player_id
        call_amount = game_state.call_amount

        if game_state.street == "preflop":
            strength = self._preflop_strength()
            facing_raise = game_state.current_bet > game_state.big_blind
            if strength >= 4 or (strength == 3 and not facing_raise):
                return self._raise(game_state, 0.75)
            if strength == 3 and call_amount <= game_state.big_blind * 4:
                return PlayerAction.call(me)
            if strength == 2 and call_amount <= game_state.big_blind * 2:
                return PlayerAction.call(me)
            if call_amount == 0:
                return PlayerAction.call(me)
            return PlayerAction.fold(me)

        board = list(game_state.board)
        made, uses_hole, draw = self._postflop_strength(board)
        pot_odds = game_state.pot_odds

        if made >= 2 or (made == 1 and uses_hole and rank_kicker(self.hand, board)):
            if game_state.can_raise and (made >= 2 or call_amount == 0):
                return self._raise(game_state, 0.75)
            return PlayerAction.call(me)

        if made == 1 and uses_hole:
            if call_amount == 0:
                return PlayerAction.call(me)
            if pot_odds <= 0.25:
                return PlayerAction.call(me)
            return PlayerAction.fold(me)

        if draw and pot_odds <= 0.25:
            if call_amount == 0:
                return self._raise(game_state, 0.5) if game_state.can_raise else PlayerAction.call(me)
            return PlayerAction.call(me)
        if call_amount == 0:
            return PlayerAction.call(me)
        return PlayerAction.fold(me)


    def end_game(
        self, actions: list[PlayerAction], game_state: GameStateView
    ):
        """
        Called after every hand, whether or not you were still in it.

        actions: everything since your last turn: the last moves, then at a
            showdown each remaining player's hole cards (reveal_card with
            that player's id; the dealer's reveal_card is a board card),
            then one win per player who won chips (amount = their total
            from every pot). A player who wins because everyone else
            folded shows nothing.
        game_state: the final state of the hand, stacks after the pot.

        Learn from the hand here. Per-hand fields need no clearing: seed()
        sets them again at the start of the next hand.
        """
        self.hands_played += 1
        for action in actions:
            if action.kind == "fold" and action.player_id != self.player_id:
                self.opponent_folds[action.player_id] = (
                    self.opponent_folds.get(action.player_id, 0) + 1
                )


def rank_kicker(hand, board):
    """Whether a made pair is likely to be a useful pair rather than a board pair."""
    board_ranks = {card.rank for card in board}
    return any(card.rank not in board_ranks and card.value >= 11 for card in hand)
