#!/usr/bin/env python
__author__ = 'jesse'

import math


def main():

    # Enumerate coordinates of rooms.
    rooms = {'3402': (0, 0),
             '3404': (1, 0),
             '3406': (0.5, 1.5),
             '3408': (2.5, 0),
             '3410': (2.5, 1.5),
             '3414': (7.5, 1),
             '3414a': (5.5, 1.5),
             '3414b': (9.5, 1.5),
             '3416': (4, 0),
             '3418': (5, 0),
             '3420': (6, 0),
             '3422': (7, 0),
             '3424': (8.5, 0),
             '3430': (10, 0),
             '3432': (11, 0),
             '3436': (12.5, 1),
             '3502': (1, 3),
             '3504': (2.5, 3),
             '3506': (4, 2),
             '3508': (4, 3),
             '3510': (5, 3),
             '3512': (6, 3),
             '3514': (7.5, 3),
             '3516': (9, 3),
             '3518': (10.5, 3),
             '3520': (7.5, 2)}
    min_x = min([rooms[r][0] for r in rooms.keys()])
    max_x = max([rooms[r][0] for r in rooms.keys()])
    min_y = min([rooms[r][1] for r in rooms.keys()])
    max_y = max([rooms[r][1] for r in rooms.keys()])

    # Get unary 'north', 'east', 'west', 'south' relationships.
    for r in rooms:
        if rooms[r][0] > (max_x - min_x) / 2.0:
            print "east(" + r + ")"
        elif rooms[r][0] < (max_x - min_x) / 2.0:
            print "west(" + r + ")"
        if rooms[r][1] > (max_y - min_y) / 2.0:
            print "south(" + r + ")"
        elif rooms[r][1] < (max_y - min_y) / 2.0:
            print "north(" + r + ")"

    # Get binary 'adjacent' relationships.
    for idx in range(len(rooms.keys())):
        a = rooms.keys()[idx]
        for jdx in range(idx+1, len(rooms.keys())):
            b = rooms.keys()[jdx]
            if math.sqrt(math.pow(rooms[a][0] - rooms[b][0], 2) + math.pow(rooms[a][1] - rooms[b][1], 2)) < 2.0:
                print "adjacent(" + a + ", " + b + ")"

    # Get binary 'northof', 'eastof', 'westof', 'southof' relationships.
    for a in rooms:
        for b in rooms:
            if a != b:
                if abs(rooms[a][0] - rooms[b][0]) < 2.0:
                    if rooms[a][0] > rooms[b][0]:
                        print "eastof(" + a + ", " + b + ")"
                    elif rooms[a][0] < rooms[b][0]:
                        print "westof(" + a + ", " + b + ")"
                if abs(rooms[a][1] - rooms[b][1]) < 2.0:
                    if rooms[a][1] > rooms[b][1]:
                        print "southof(" + a + ", " + b + ")"
                    elif rooms[a][1] < rooms[b][1]:
                        print "northof(" + a + ", " + b + ")"


if __name__ == '__main__':
    main()
