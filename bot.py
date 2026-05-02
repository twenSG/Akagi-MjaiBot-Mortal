import json
import sys

import model
from libriichi.state import PlayerState  # type: ignore[import-not-found]
from meta_show import meta_to_top_show

class Bot:
    def __init__(self):
        self.player_id: int = None
        self.model = None
        self.state: PlayerState | None = None
        # ========== Online Server =========== #
        model.online_settings_init()
        # ==================================== #

    def react(self, events: str) -> str:
        """
        # How to implement this function

        One `start_game` event must be sent before any other events.
        Once the bot receives a `start_game` event, it will reinitialize itself and set the player_id.

        `start_game` event can be sent any time to reset the bot.
        `end_game` event can be sent to set model to None.

        :param events: JSON string of events
        :return: JSON string of action

        Example:
        ```
        bot = Bot()
        res = bot.react('[{"type":"start_game","names":["0","1","2","3"],"id":0}]')
        # res == '{"type":"none"}'

        events = str([
            {
                "type":"start_kyoku",
                "bakaze":"S",
                "dora_marker":"1p",
                "kyoku":2,"honba":2,
                "kyotaku":0,
                "oya":1,
                "scores":[800,61100,11300,26800],
                "tehais":[
                    ["4p","4s","P","3p","1p","5s","2m","F","1m","7s","9m","6m","9s"],
                    ["?","?","?","?","?","?","?","?","?","?","?","?","?"],
                    ["?","?","?","?","?","?","?","?","?","?","?","?","?"],
                    ["?","?","?","?","?","?","?","?","?","?","?","?","?"]
                ]
            },
            {"type":"tsumo","actor":1,"pai":"?"},
            {"type":"dahai","actor":1,"pai":"F","tsumogiri":false},
            {"type":"tsumo","actor":2,"pai":"?"},
            {"type":"dahai","actor":2,"pai":"3m","tsumogiri":true},
            {"type":"tsumo","actor":3,"pai":"?"},
            {"type":"dahai","actor":3,"pai":"1m","tsumogiri":true},
            {"type":"tsumo","actor":0,"pai":"3s"}
        ])

        res = bot.react(events)
        # res == '{"type":"dahai","pai":"3s","actor":0,"tsumogiri":true}'
        ...        
        res = bot.react('[{"type":"start_game","names":["0","1","2","3"],"id":3}]')
        # res == '{"type":"none"}'
        ...
        ```

        For more information, please refer to https://github.com/smly/mjai.app
        """
        try:
            events = json.loads(events)
        except json.JSONDecodeError as e:
            return json.dumps({"type":"none"}, separators=(",", ":"))

        return_action = None
        for e in events:
            if e["type"] == "start_game":
                self.player_id = e["id"]
                self.model = model.load_model(self.player_id)
                self.state = PlayerState(self.player_id)
                continue
            if self.model is None or self.player_id is None:
                continue
            if e["type"] == "end_game":
                self.player_id = None
                self.model = None
                self.state = None
                continue
            event_json = json.dumps(e, separators=(",", ":"))
            return_action = self.model.react(event_json)
            # Mirror the bot's view of the game on a parallel PlayerState
            # so we can resolve chi/pon/kan/hora tiles for `meta.show`.
            # Failures here must never poison the action returned to the
            # host — log + continue.
            if self.state is not None:
                try:
                    self.state.update(event_json)
                except Exception as exc:
                    sys.stderr.write(f"player_state.update failed: {exc}\n")
                    sys.stderr.flush()

        if return_action is None:
            # ========== Online Server =========== #
            if model.ot_settings['online']:
                raw_data = {
                    "type":"none",
                    "meta": {
                        "online": model.is_online
                    }
                }
                return_action = json.dumps(raw_data, separators=(",", ":"))
            else:
                return_action = json.dumps({"type":"none"}, separators=(",", ":"))
            # ==================================== #
            return return_action
        else:
            raw_data = json.loads(return_action)
            # ========== Online Server =========== #
            if model.ot_settings['online']:
                if "meta" in raw_data:
                    raw_data["meta"]["online"] = model.is_online
                else:
                    raw_data["meta"] = {"online": model.is_online}
            # ==================================== #
            # Top-3 from q_values + mask_bits → meta.show. Skipped when
            # the bot didn't emit q_values (e.g. degenerate `none`).
            meta = raw_data.get("meta")
            if meta and "q_values" in meta and "mask_bits" in meta and self.state is not None:
                try:
                    show = meta_to_top_show(meta, self.state, is_3p=False)
                    if show.get("items"):
                        meta["show"] = show
                except Exception as exc:
                    sys.stderr.write(f"meta_to_top_show failed: {exc}\n")
                    sys.stderr.flush()
            return json.dumps(raw_data, separators=(",", ":"))

def main() -> None:
    bot = Bot()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            resp = bot.react(line)
        except Exception as e:  # never crash the loop
            sys.stderr.write(f"bot error: {e}\n")
            sys.stderr.flush()
            resp = json.dumps({"type": "none"}, separators=(",", ":"))
        sys.stdout.write(resp + "\n")
        sys.stdout.flush()
        try:
            evs = json.loads(line)
        except Exception:
            continue
        if any(ev.get("type") == "end_game" for ev in evs):
            break


if __name__ == "__main__":
    main()
