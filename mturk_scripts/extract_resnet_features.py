#!/usr/bin/env python
__author__ = 'jesse'

import argparse
import numpy as np
import os
import pickle
import torch
import torch.nn as nn
from PIL import Image
import torch.nn.functional as F
from torchvision.models import resnet
from torchvision.transforms import ToTensor
from torchvision.transforms import Normalize
from torchvision.transforms.functional import resize


def vecs_from_models(fn, resnet_m, plm, tt, normalize):
    pil = Image.open(fn)
    pil = resize(pil, (224, 224))  # original 3024x3024, so resize to square min 224x224
    im = tt(pil)
    im = normalize(im)
    im = torch.unsqueeze(im, 0)
    plm_v = plm(im).detach().data.numpy().flatten()
    fl_v = F.softmax(resnet_m(im), dim=1).detach().data.numpy().flatten()
    return plm_v, fl_v


def main(args):

    # Load existing features file.
    print("Loading existing object features...")
    with open(args.features_infile, 'rb') as f:
        feats = pickle.load(f)
    print("... done")

    print("Running ResNet-152 on object images in '" + args.images_dir + "'...")
    resnet_m = resnet.resnet152(pretrained=True)  # Full model
    plm = nn.Sequential(*list(resnet_m.children())[:-1])  # Penultimate layer
    for param in plm.parameters():
        param.requires_grad = False
    tt = ToTensor()
    # https://github.com/pytorch/examples/blob/42e5b996718797e45c46a25c55b031e6768f8440/imagenet/main.py#L89-L101
    normalize = Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])  # bc of imagenet pretraining
    for oidx in range(len(feats)):
        print("... extracting for oidx " + str(oidx))

        if args.five_trial == 0:
            fn = os.path.join(args.images_dir, 'oidx_' + str(oidx) + '.jpg')
            plm_v, fl_v = vecs_from_models(fn, resnet_m, plm, tt, normalize)

            if 'resnet152-pul' not in feats[oidx]['look']:
                feats[oidx]['look']['resnet152-pul'] = []
            feats[oidx]['look']['resnet152-pul'].append(plm_v)
            if 'resnet152-fl' not in feats[oidx]['look']:
                feats[oidx]['look']['resnet152-fl'] = []
            feats[oidx]['look']['resnet152-fl'].append(fl_v)

            print(fn, 'resnet152-pul', min(plm_v), np.average(plm_v), max(plm_v), len(plm_v))  # DEBUG
            print(fn, 'resnet152-fl', min(fl_v), np.average(fl_v), max(fl_v), len(fl_v))  # DEBUG

        else:
            for t in range(1, 6):  # t=1,2,3,4,5
                print("...... extracting for trial " + str(t))
                avg_plm_v = avg_fl_v = None
                num_imgs = 0
                fp = os.path.join(args.images_dir, "t" + str(t), "obj_" + str(oidx+1),  # obs 1-indexed in orig data
                                  "trial_1", "look", "vision_data")
                for _, _, fs in os.walk(fp):
                    for fn in fs:
                        if fn.split('.')[-1] == 'jpg':
                            plm_v, fl_v = vecs_from_models(os.path.join(fp, fn), resnet_m, plm, tt, normalize)
                            if avg_plm_v is None:
                                avg_plm_v = plm_v
                                avg_fl_v = fl_v
                            else:
                                avg_plm_v += plm_v
                                avg_fl_v += fl_v
                            num_imgs += 1

                if avg_plm_v is not None:
                    avg_plm_v /= num_imgs
                    avg_fl_v /= num_imgs

                    if 'resnet152-pul' not in feats[oidx]['look']:
                        feats[oidx]['look']['resnet152-pul'] = []
                    feats[oidx]['look']['resnet152-pul'].append(avg_plm_v)
                    if 'resnet152-fl' not in feats[oidx]['look']:
                        feats[oidx]['look']['resnet152-fl'] = []
                    feats[oidx]['look']['resnet152-fl'].append(avg_fl_v)

                    # print('resnet152-pul', min(avg_plm_v), np.average(avg_plm_v),
                    #       max(avg_plm_v), len(avg_plm_v))  # DEBUG
                    # print('resnet152-fl', min(avg_fl_v), np.average(avg_fl_v),
                    #       max(avg_fl_v), len(avg_fl_v))  # DEBUG
                else:
                    print('WARNING: no features extracted for trial ' + str(t) + ', oidx ' + str(oidx))
                print("......... done")
        print("...... done")

    print("... done")

    print("Writing new object features...")
    with open(args.features_outfile, 'wb') as f:
        pickle.dump(feats, f)
    print("... done")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--features_infile', type=str, required=True,
                        help="object features infile")
    parser.add_argument('--images_dir', type=str, required=True,
                        help="directory where object images to extract features from live")
    parser.add_argument('--five_trial', type=int, required=True,
                        help="whether this is a five trial directory (1 if so, 0 otherwise)")
    parser.add_argument('--features_outfile', type=str, required=True,
                        help="object features outfile")
    args = parser.parse_args()
    main(args)
