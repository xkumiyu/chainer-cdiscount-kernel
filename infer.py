import argparse
from collections import defaultdict
import os

import chainer
from chainer.dataset import convert
import chainer.functions as F
import chainer.links as L
import numpy as np
import pandas as pd
from tqdm import tqdm

from dataset import DatasetwithJPEG
from model import ResNet152


def main():
    parser = argparse.ArgumentParser(description='Predict')
    parser.add_argument('dataset', help='Path to test image-label')
    parser.add_argument('--gpu', '-g', type=int, default=-1,
                        help='GPU ID (negative value indicates CPU)')
    parser.add_argument('--batchsize', '-b', type=int, default=32,
                        help='Number of images in each mini-batch')
    parser.add_argument('--out', '-o', default='result',
                        help='Directory to output the result')
    parser.add_argument('--model', '-m', default='model.npz')
    parser.add_argument('--labels', '-l', default='labels.csv')
    parser.add_argument('--crops', '-c', type=int, default=0)
    args = parser.parse_args()

    print('GPU: {}'.format(args.gpu))
    print('# minibatch size: {}'.format(args.batchsize))

    # Dataset
    all_files = os.listdir(args.dataset)
    image_files = [(f, f.split('-')[0]) for f in all_files if ('png' in f or 'jpg' in f)]
    if args.crops > 0:
        dataset = DatasetwithJPEG(image_files, args.dataset, True)
    else:
        dataset = DatasetwithJPEG(image_files, args.dataset)
    n_classes = 5270

    labels = pd.read_csv(args.labels)
    label_to_categpry = dict(zip(labels.index, labels['category_id']))

    print('# samples: {}'.format(len(dataset)))
    print('# data shape: {}'.format(dataset[0][0].shape))
    print('# number of label: {}'.format(n_classes))
    print('')

    # Model
    model = L.Classifier(ResNet152(n_classes))
    chainer.serializers.load_npz(os.path.join(args.out, args.model), model)
    if args.gpu >= 0:
        chainer.cuda.get_device_from_id(args.gpu).use()
        model.to_gpu()

    # Iterator
    test_iter = chainer.iterators.SerialIterator(
        dataset, args.batchsize, repeat=False, shuffle=False)
    n_iter = int(len(dataset) / args.batchsize)

    # Infer
    def predict(test_iter, y_pred, pbar):
        for batch in test_iter:
            x_array, _id_array = convert.concat_examples(batch, args.gpu)
            y_array = F.softmax(model.predictor(x_array)).data

            if args.gpu >= 0:
                _id_array = chainer.cuda.to_cpu(_id_array)
                y_array = chainer.cuda.to_cpu(y_array)

            for _id, y in zip(list(_id_array), y_array):
                y_pred[_id].append(y)
            pbar.update()
        return y_pred

    y_pred = defaultdict(list)
    if args.crops > 0:
        pbar = tqdm(total=n_iter * args.crops)
        for _ in range(args.crops):
            y_pred = predict(test_iter, y_pred, pbar)
    else:
        pbar = tqdm(total=n_iter)
        y_pred = predict(test_iter, y_pred, pbar)
    pbar.close()

    def select_category(y):
        label = np.asarray(y).sum(axis=0).argmax()
        category_id = label_to_categpry[label]
        return category_id

    result = [(_id, select_category(y)) for _id, y in y_pred.items()]
    df = pd.DataFrame(result,  columns=['_id', 'category_id'])
    df = df.set_index('_id')

    df.to_csv(os.path.join(args.out, 'submission.csv.gz'), compression='gzip')

    # correct products size: 1768182
    print('Inference Finished: {} products'.format(len(df)))


if __name__ == '__main__':
    main()
