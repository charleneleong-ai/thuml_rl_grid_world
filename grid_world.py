import numpy as np
import copy
import scipy.io as sio
import random
# Maze state is represented as a 2-element NumPy array: (Y, X). Increasing Y is South.
# Possible actions, expressed as (delta-y, delta-x).

maze_actions = {
    'N': np.array([-1, 0]),
    'S': np.array([1, 0]),
    'E': np.array([0, 1]),
    'W': np.array([0, -1]),
}


def parse_topology(topology):
    return np.array([list(row) for row in topology])


class Maze(object):
    """
    Simple wrapper around a NumPy 2D array to handle flattened indexing and staying in bounds.
    """
    def __init__(self, topology):
        self.topology = parse_topology(topology)
        self.flat_topology = self.topology.ravel()
        self.shape = self.topology.shape

    def in_bounds_flat(self, position):
        return 0 <= position < np.product(self.shape)

    def in_bounds_unflat(self, position):
        return 0 <= position[0] < self.shape[0] and 0 <= position[1] < self.shape[1]

    def get_flat(self, position):
        if not self.in_bounds_flat(position):
            raise IndexError("Position out of bounds: {}".format(position))
        return self.flat_topology[position]

    def get_unflat(self, position):
        if not self.in_bounds_unflat(position):
            raise IndexError("Position out of bounds: {}".format(position))
        return self.topology[tuple(position)]


    def flatten_index(self, index_tuple):
        return np.ravel_multi_index(index_tuple, self.shape)

    def unflatten_index(self, flattened_index):
        return np.unravel_index(flattened_index, self.shape)

    def flat_positions_containing(self, x):
        return list(np.nonzero(self.flat_topology == x)[0])

    def flat_positions_not_containing(self, x):
        return list(np.nonzero(self.flat_topology != x)[0])

    def __str__(self):
        return '\n'.join(''.join(row) for row in self.topology.tolist())

    def __repr__(self):
        return 'Maze({})'.format(repr(self.topology.tolist()))

def move_avoiding_walls(maze, position, action):
    """
    Return the new position after moving, and the event that happened ('hit-wall' or 'moved').
    Works with the position and action as a (row, column) array.
    """
    # Compute new position

    new_position = position + action
    # Compute collisions with walls, including implicit walls at the ends of the world.
    if not maze.in_bounds_unflat(new_position) or maze.get_unflat(new_position) == '#':
        return position, 'hit-wall'

    return new_position, 'moved'



class GridWorld(object):
    """
    A simple task in a maze: get to the goal.
    Parameters
    ----------
    maze : list of strings or lists
        maze topology (see below)

    rewards: dict of string to number. default: {'*': 10}.
        Rewards obtained by being in a maze grid with the specified contents,
        or experiencing the specified event (either 'hit-wall' or 'moved'). The
        contributions of content reward and event reward are summed. For
        example, you might specify a cost for moving by passing
        rewards={'*': 10, 'moved': -1}.

    terminal_markers: sequence of chars, default '-'
        A grid cell containing any of these markers will be considered a
        "terminal" state.

    action_error_prob: float
        With this probability, the requested action is ignored and a random
        action is chosen instead.

    Notes
    -----

    Maze topology is expressed textually. Key:
     '#': wall
     '.': open (really, anything that's not '#')
     '*': goal
     'o': origin
     'X': pitfall
    """

    def __init__(self, maze, rewards={'*': 1.0}, terminal_markers='-', action_error_prob=0.2, directions="NSEW"):
        self.maze = Maze(maze) if not isinstance(maze, Maze) else maze
        self.rewards = rewards
        self.terminal_markers = terminal_markers
        self.action_error_prob = action_error_prob

        for x in range(self.maze.shape[0]):
        	for y in range(self.maze.shape[1]):
        		if self.maze.topology[x][y] == 'o':
        			self.origin = (x, y)
        self.actions = [maze_actions[direction] for direction in directions]
        self.num_actions = len(self.actions)
        self.state = None
        self.reset()
        self.num_states = self.maze.shape[0] * self.maze.shape[1]

    def __repr__(self):
        return 'GridWorld(maze={maze!r}, rewards={rewards}, terminal_markers={terminal_markers}, action_error_prob={action_error_prob})'.format(**self.__dict__)

    def reset(self):
        """
        Reset the position to a starting position (an 'o'), chosen at random.
        """
        options = self.maze.flat_positions_containing('o')
        self.state = options[ np.random.choice(len(options)) ]

    def is_terminal(self, state):
        """Check if the given state is a terminal state."""
        return self.maze.get_flat(state) in self.terminal_markers

    def observe(self):
        """
        Return the current state as an integer.
        The state is the index into the flattened maze.
        """
        return self.state


    def perform_action(self, action_idx):
        """Perform an action (specified by index), yielding a new state and reward."""
        # In the absorbing end state, nothing does anything.
        if self.is_terminal(self.state):
            return self.observe(), 0

        if self.action_error_prob and np.random.rand() < self.action_error_prob:
            # finale! this would be just pick any direction; we
            # changed it to be slip 90-degrees in some direction
            # action_idx = np.random.choice(self.num_actions)
            if np.random.rand() < .5:
                if action_idx == 0 or action_idx == 1:
                    action_idx = 2
                else: 
                    action_idx = 0
            else: 
                if action_idx == 0 or action_idx == 1:
                    action_idx = 3
                else: 
                    action_idx = 1
           

        action = self.actions[action_idx]

        new_state_tuple, result = move_avoiding_walls(self.maze, self.maze.unflatten_index(self.state), action)
        self.state = self.maze.flatten_index(new_state_tuple)
        reward = self.rewards.get(self.maze.get_flat(self.state), 0) + self.rewards.get(result, 0)
        return self.observe(), reward

    def as_mdp(self):
        transition_probabilities = np.zeros((self.num_states, self.num_actions, self.num_states))
        rewards = np.zeros((self.num_states, self.num_actions, self.num_states))
        action_rewards = np.zeros((self.num_states, self.num_actions))
        destination_rewards = np.zeros(self.num_states)

        for state in range(self.num_states):
            destination_rewards[state] = self.rewards.get(self.maze.get_flat(state), 0)

        is_terminal_state = np.zeros(self.num_states, dtype=np.bool)

        for state in range(self.num_states):
            if self.is_terminal(state):
                is_terminal_state[state] = True
                transition_probabilities[state, :, state] = 1.
            else:
                for action in range(self.num_actions):
                    new_state_tuple, result = move_avoiding_walls(self.maze, self.maze.unflatten_index(state), self.actions[action])
                    new_state = self.maze.flatten_index(new_state_tuple)
                    transition_probabilities[state, action, new_state] = 1.
                    action_rewards[state, action] = self.rewards.get(result, 0)

        # Now account for action noise.
        transitions_given_random_action = transition_probabilities.mean(axis=1, keepdims=True)
        transition_probabilities *= (1 - self.action_error_prob)
        transition_probabilities += self.action_error_prob * transitions_given_random_action

        rewards_given_random_action = action_rewards.mean(axis=1, keepdims=True)
        action_rewards = (1 - self.action_error_prob) * action_rewards + self.action_error_prob * rewards_given_random_action
        rewards = action_rewards[:, :, None] + destination_rewards[None, None, :]
        rewards[is_terminal_state] = 0
        return transition_probabilities, rewards

    def get_max_reward(self):
        transition_probabilities, rewards = self.as_mdp()
        return rewards.max()





def Value_iteration(transition_prob, rewds, num_states, num_actions, discount=0.9):

    discounted_V = np.zeros(num_states)

    for t in range(100):
        #TODO: fill in the implementation of value iteration here 
        v_prev = copy.deepcopy(discounted_V)

        for s in range(num_states):
            q_max =0
            for a in range(num_actions):
                q_a = 0
                for s1 in range(num_states):
                    q_a = q_a + transition_prob[s][a][s1] * (rewds[s][a][s1] + discount * v_prev[s1])

                if q_a > q_max:
                    q_max = q_a
        
            discounted_V = q_max

        #END
    return discounted_V


def Q_learning(grid_world, timehorizon = 15, discount=0.9, learning_rate=0.5):
    n, m = grid_world.maze.shape
    num_states = grid_world.num_states
    num_actions = grid_world.num_actions
    Q_value = np.zeros((num_states, num_actions))

    rew_sum = np.zeros((num_states, num_actions))
    cnt = np.zeros((num_states, num_actions))
    """
    action: up, down, left, right
    -------------
    0 | 1 | 2| 3|
    """
    actions = [0, 1, 2, 3]

    sum_rewards = 0
    epsilon = 0.9

    learning_rate_min = 0.0001
    
    for rounds in range(500):
        grid_world.reset()

        traj = []
        for t in range(timehorizon):
            state = copy.deepcopy(grid_world.state)

            # set default action
            act = None 

            #TODO: use epsilon greedy to choose an action to take 

            if np.random.rand()<epsilon:            
                act = np.random.choice(actions)
            else:
               act = np.argmax(Q_value[state])

            

            #END
            next_state, rew = grid_world.perform_action(act)
            sum_rewards += rew 
            traj.append((state, act, rew, next_state))

            #TODO: update Q-value for state action pair
            Q_value[state][act]= Q_value[state][act]+learning_rate*(rew+discount*Q_value[next_state][np.argmax(Q_value[next_state])]-Q_value[state][act])
            #END 
            
            cnt[state][act] = cnt[state][act] + 1

        #TODO: you can fill in code here if necessary.
        
        # decay the learning rate 
        if learning_rate > learning_rate_min:
            learning_rate = learning_rate * (1 - 0.005)

        #END 

	return sum_rewards, Q_value




maze = [['.', '.', '.', '.', '.', '.'],
		['.', '*', '*', '*', '*', '.'],
		['.', '.', '*', '.', '*', '.'],
		['.', '*', '.', '#', '*', '.'],
		['.', '.', '#', '#', '.', '.'],
		['.', 'o', '.', '#', '.', '.']]




grid_world = GridWorld(maze)



r, q = Q_learning(grid_world)

transition_prob, rewds = grid_world.as_mdp()
v = Value_iteration(transition_prob, rewds, grid_world.num_states, grid_world.num_actions)

sio.savemat("value_iter", {"v":v})
sio.savemat("q_learning", {"rew":r, "q": q})
