from __future__ import division
import numpy as np
import tensorflow as tf

from ..base import \
    scoped_variable, _validate_axes


def affine(X, dim_out, name='', scope_name='affine'):
    """ Affine: X*W + b
        X has shape [batch, dim_in]
        Then W, b will be [dim_in, dim_out], [1, dim_out]
    """
    assert X.get_shape().ndims == 2
    dim_in = X.get_shape()[1]
    W = scoped_variable('w_%s' % name,
                        scope_name,
                        shape=(dim_in, dim_out), dtype=tf.float32,
                        initializer=tf.contrib.layers.xavier_initializer())
    b = scoped_variable('b_%s' % name,
                        scope_name,
                        shape=(dim_out,), dtype=tf.float32)

    return tf.nn.xw_plus_b(X, W, b, 'affine_%s' % name)


def make_stack(func):
    def generic_stack(X, params, nonlin, name,
                      raw_output=True,
                      initializer=tf.truncated_normal_initializer(stddev=0.1)):
        if not isinstance(nonlin, list):
            nonlin = [nonlin] * len(params)
        for i, param in enumerate(params):
            X = func(X, param, i, name)
            if not raw_output or i + 1 < len(params):
                X = nonlin[i](X)
        return X
    return generic_stack


def norm(X, axis=None, keep_dims=False, p=2, root=True):
    """
    Compute the norm of a tensor across the given axes.
    Like np.linalg.norm.

    :param X: a Tensor of arbitrary dimensions
    :param axis: an int, list(int), or None
    :param keep_dims: bool
    :param p: float > 0
    """
    axis = _validate_axes(axis)
    Y = tf.reduce_sum(tf.pow(X, p), axis, keep_dims)
    if not root:
        return Y
    else:
        return tf.pow(Y, 1.0 / p)


def normalize(X, axis):
    """
    Normalize a Tensor so that it sums to one across the given axis.
    """
    axis = _validate_axes(axis)
    return X / tf.reduce_sum(X, axis, keep_dims=True)
