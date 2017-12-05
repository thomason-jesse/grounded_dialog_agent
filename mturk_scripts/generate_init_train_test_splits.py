#!/usr/bin/env python
__author__ = 'jesse'

import argparse
import json
import os
import random


def main():

    # Load parameters from command line.
    init_size = FLAGS_init_size
    train_size = FLAGS_train_size
    test_size = FLAGS_test_size
    outdir = FLAGS_outdir
    assert init_size + train_size + test_size == 1

    # Enumerate rooms, people, and (fixed) test objects
    rooms = ['3402', '3404', '3406', '3408', '3410', '3414', '3414a', '3414b', '3416', '3418', '3420',
             '3422', '3424', '3430', '3432', '3436', '3502', '3504', '3506', '3508', '3510', '3512',
             '3514', '3516', '3518', '3520']
    people = ['h', 'n', 'd', 'w', 's', 'm', 'p', 'b', 'r']
    objects = ['oidx_22', 'oidx_28', 'oidx_12', 'oidx_25', 'oidx_11', 'oidx_6', 'oidx_26', 'oidx_13']

    # Enumerate all walking tasks.
    walking_tasks = []
    for r in rooms:
        task = {'action': 'walk', 'goal': r}
        walking_tasks.append(task)

    # Emumerate all delivery tasks.
    delivery_tasks = []
    for p in people:
        for o in objects:
            task = {'action': 'bring', 'patient': o, 'recipient': p}
            delivery_tasks.append(task)

    # Enumerate all relocation tasks.
    relocation_tasks = []
    for o in objects:
        for s in rooms:
            for g in rooms:
                if s != g:
                    task = {'action': 'move', 'patient': o, 'source': s, 'goal': g}
                    relocation_tasks.append(task)

    # Create and print task splits.
    walking_tasks_settings = {}
    delivery_tasks_settings = {}
    relocation_tasks_settings = {}
    for task_name, task_type, tasks in [('walking', walking_tasks_settings, walking_tasks),
                                        ('delivery', delivery_tasks_settings, delivery_tasks),
                                        ('relocation', relocation_tasks_settings, relocation_tasks)]:

        num_init = int(init_size * len(tasks) + 0.5)
        if num_init == 0 and init_size > 0:
            num_init = 1
        task_type['init'] = random.sample(tasks, num_init)

        num_train = int(train_size * len(tasks) + 0.5)
        if num_train == 0 and train_size > 0:
            num_train = 1
        task_type['train'] = random.sample([t for t in tasks if t not in task_type['init']], num_train)

        task_type['test'] = [t for t in tasks if t not in task_type['init'] and t not in task_type['train']]

    # Write goals to json files.
    for task_name, task_type in [('walking', walking_tasks_settings),
                                        ('delivery', delivery_tasks_settings),
                                        ('relocation', relocation_tasks_settings)]:
        for setting in ['init', 'train', 'test']:
            fn = os.path.join(outdir, task_name + "_" + setting + ".json")
            with open(fn, 'w') as f:
                json.dump(task_type[setting], f)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--init_size', type=float, required=True,
                        help="portion [0-1] of tasks to be in init fold")
    parser.add_argument('--train_size', type=float, required=True,
                        help="portion [0-1] of tasks to be in train fold")
    parser.add_argument('--test_size', type=float, required=True,
                        help="portion [0-1] of tasks to be in test fold")
    parser.add_argument('--outdir', type=str, required=True,
                        help="directory to write goal splits")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
