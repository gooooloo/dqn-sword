
import types
import gym

import numpy as np
from easydict import EasyDict as edict
from gymgame.engine import Vector2
from gymgame.tinyrpg.sword import config, Serializer, EnvironmentGym
from gymgame.tinyrpg.framework import Skill, Damage, SingleEmitter
from gym import spaces

HRA_NUM_ACTIONS = 9

OB_LENGTH = 12
OB_SPACE_SHAPE = [OB_LENGTH]


GAME_NAME = config.GAME_NAME

config.BOKEH_MODE = "bokeh_serve"  # you need run `bokeh serve` firstly

config.MAP_SIZE = Vector2(30, 30)

config.GAME_PARAMS.fps = 24

config.GAME_PARAMS.max_steps = 300

config.NUM_PLAYERS = 1

config.NUM_NPC = 1

config.PLAYER_INIT_RADIUS = (0.0, 0.0)

config.NPC_INIT_RADIUS = (0.1, 0.1)

config.NPC_SKILL_COUNT = 1

config.SKILL_DICT = {
    'normal_attack' : Skill(
        id = 'normal_attack',
        cast_time = 0.0,#0.1,
        mp_cost = 0,
        target_required = True,
        target_relation = config.Relation.enemy,
        cast_distance = 1.0,
        target_factors = [Damage(200.0, config.Relation.enemy)]
    ),

    'normal_shoot' : Skill(
        id = 'normal_shoot',
        cast_time = 0.0, #0.3,
        mp_cost = 0,
        bullet_emitter = SingleEmitter(
            speed=0.3 * config.GAME_PARAMS.fps,
            penetration=1.0,
            max_range=config.MAP_SIZE.x * 0.8,
            radius=0.1,
            factors=[Damage(5.0, config.Relation.enemy)])
    ),

    'puncture_shoot' : Skill(
        id = 'normal_shoot',
        cast_time = 0.0,#0.3,
        mp_cost = 0,
        bullet_emitter = SingleEmitter(
            speed=0.3 * config.GAME_PARAMS.fps,
            penetration=np.Inf,
            max_range=config.MAP_SIZE.x * 0.8,
            radius=0.1,
            factors=[Damage(5.0, config.Relation.enemy)])
    ),
}

config.PLAYER_SKILL_LIST = [config.SKILL_DICT['puncture_shoot']]

config.NPC_SKILL_LIST = [config.SKILL_DICT['normal_attack']]

config.BASE_PLAYER = edict(
    id = "player-{0}",
    position = Vector2(0, 0),
    direct = Vector2(0, 0),
    speed = 0.3 * config.GAME_PARAMS.fps,
    radius = 0.5,
    max_hp = 100.0,
    camp = config.Camp[0],
    skills=config.PLAYER_SKILL_LIST
)

config.BASE_NPC = edict(
    id = "npc-{0}",
    position = Vector2(0, 0),
    direct = Vector2(0, 0),
    speed = 0.1 * config.GAME_PARAMS.fps,
    radius = 0.5,
    max_hp = 400.0,
    camp = config.Camp[1],
    skills=config.NPC_SKILL_LIST
)


def myextension(cls):

    def decorate_extension(ext_cls):
        dict = ext_cls.__dict__
        for k, v in dict.items():
            if type(v) is not types.MethodType and \
                            type(v) is not types.FunctionType and \
                            type(v) is not property:
                continue
            if hasattr(cls, k):
                setattr(cls, k+'_orig', getattr(cls, k))
            setattr(cls, k, v)
        return ext_cls

    return decorate_extension


@myextension(Serializer)
class SerializerExtension():

    DIRECTS = [Vector2.up,
               Vector2.up + Vector2.right,
               Vector2.right,
               Vector2.right + Vector2.down,
               Vector2.down,
               Vector2.down + Vector2.left,
               Vector2.left,
               Vector2.left + Vector2.up,
               ]

    def _deserialize_action(self, data):
        index, target = data
        if index < 8:
            direct = SerializerExtension.DIRECTS[index]
            actions = [('player-0', config.Action.move_toward, direct, None)]

        else:
            skill_index = index - 8
            skill_id = config.BASE_PLAYER.skills[skill_index].id
            actions = [('player-0', config.Action.cast_skill, skill_id, target, None)]

        return actions

    def _serialize_map(self, k, map):
        s_players = k.do_object(map.players, self._serialize_player)
        s_npcs = k.do_object(map.npcs, self._serialize_npc)
        s_bullets = []

        return np.hstack([s_players, s_npcs, s_bullets])

    def _serialize_character(self, k, char):

        # def norm_position_relative(v, norm):
        #     map = norm.game.map
        #     player = map.players[0]
        #     return (v - player.attribute.position) / map.bounds.max

        def norm_position_abs(v, norm):
            map = norm.game.map
            return v / map.bounds.max

        attr = char.attribute
        k.do(attr.position, None, norm_position_abs)
        k.do(attr.hp, None, k.n_div_tag, config.Attr.hp)


@myextension(EnvironmentGym)
class EnvExtension():
    def _init_action_space(self): return spaces.Discrete(9)

    def _my_state(self):
        map = self.game.map
        player, npcs = map.players[0], map.npcs
        if len(npcs) == 0:
            delta = 0, 0
            npc_hp = 0
        else:
            delta = npcs[0].attribute.position - player.attribute.position  # [2]
            npc_hp = npcs[0].attribute.hp

        if 0 <= self._my_last_act < 9:
            tmp = np.eye(9)[self._my_last_act]
        else:
            tmp = np.zeros(9)
        max_x, max_y = config.MAP_SIZE[0], config.MAP_SIZE[1]
        s = np.concatenate([tmp, [delta[0]/max_x, delta[1]/max_y, npc_hp]])

        assert len(s) == OB_LENGTH

        return np.asarray(s)

    def _my_get_hps(self):
        map = self.game.map
        player, npcs = map.players[0], map.npcs
        return player.attribute.hp / player.attribute.max_hp, sum([o.attribute.hp / o.attribute.max_hp for o in npcs])

    def reset(self, lstmstate):
        self.reset_orig()

        self._my_last_act = -1

        return np.asarray([self._my_state(), lstmstate])

    def step(self, act, lstm_state):
        self.last_hps = self._my_get_hps()
        self.last_act = act
        self.last_pos = self.game.map.players[0].attribute.position

        _, r, t, i = self.step_orig((act, self.game.map.npcs[0]))

        self._my_last_act = act

        return np.asarray([self._my_state(), lstm_state]), r, t, i

    def _reward(self):
        hps = self._my_get_hps()
        delta_hps = hps[0] - self.last_hps[0], hps[1] - self.last_hps[1]

        return 2*delta_hps[0] -delta_hps[1]


    def npc_hp(self):
        return self._my_get_hps()[1]


def make_env():
    env = gym.make(GAME_NAME).unwrapped
    env.observation_space = gym.spaces.Box(np.inf, np.inf, OB_SPACE_SHAPE)
    return env
