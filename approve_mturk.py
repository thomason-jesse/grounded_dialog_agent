#!/usr/bin/env python
__author__ = 'jesse'

import argparse
import csv
import hashlib


def main():
    
    with open(FLAGS_csv, 'r') as f:

        inreader = csv.reader(f)
        first = True
        valid = 0
        total = 0
        ids_seen = []
        survey_header = None
        for row in inreader:

            if first:
                survey_header = row.index("Answer.surveycode")
                id_header = row.index("WorkerId")
                first = False

            else:
                code = row[survey_header]
                if '_' in code:
                    gen_id, id_hash = code.split('_')
                    true_hash = hashlib.sha1("phm_salted_hash" + gen_id + "rwhpidcwha_-1").hexdigest()[:13]
                    if id_hash != true_hash:
                        print (row[id_header] + " gen id " + gen_id +
                               " gave hash " + id_hash + " != " + true_hash)
                    elif id_hash in ids_seen:
                        print row[id_header] + " gen id " + gen_id + " already seen"
                    else:
                        valid += 1
                else:
                    print row[id_header] + " gen id " + gen_id + " invalid code " + code
                total += 1
                ids_seen.append(gen_id)
        print str(valid) + " workers of " + str(total) + " were valid"


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', type=str, required=True,
                        help="input csv")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
