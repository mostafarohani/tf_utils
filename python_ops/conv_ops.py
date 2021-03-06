from __future__ import division
import numpy as np
import tensorflow as tf

from ..base import scoped_variable, \
    _default_value, _validate_axes


def _constant_pad(X, ker_shape):
    """
    Padding type `padding='CONSTANT'` for `tf.nn.conv2d`.
    Instead of padding `X` with zeros, like `SAME` does,
    use the values on the edges.
    """
    assert X.get_shape().ndims == 4
    assert len(ker_shape) == 4

    kw, kh = ker_shape[:2]
    wb, wa = kw // 2, kw - kw // 2 - 1
    hb, ha = kh // 2, kh - kh // 2 - 1

    X_ = tf.concat(1, [
        tf.tile(X[:, :1], (1, wb, 1, 1)),
        X,
        tf.tile(X[:, -1:], (1, wa, 1, 1)),
    ])

    X_pad = tf.concat(2, [
        tf.tile(X_[:, :, :1], (1, 1, hb, 1)),
        X_,
        tf.tile(X_[:, :, -1:], (1, 1, ha, 1)),
    ])

    return X_pad


def conv(X, param, name, scope_name='conv'):
    """
    Convolution:
    `X` has shape `[B, W, H, C_in]`.
    `params['kernel']` is a tuple `(kw, kh, C_out)`.
    `params['stride']` is `(1, stride_w, stride_h, 1)` and defaults to `(1, 1, 1, 1)`.
    `params['pad']` is one of `SAME` (default), `VALID`, `CONSTANT`.
    """
    assert X.get_shape().ndims == 4

    _default_value(param, 'stride', (1, 1, 1, 1))
    _default_value(param, 'pad', 'SAME')

    kw, kh, c_out = param['kernel']
    c_in = X.get_shape()[3].value

    if param.get('bias'):
        c_in += 1
        X = tf.concat(3, [
            X, tf.ones(tf.concat(0, [tf.shape(X)[:3], [1]]))
        ])

    ker_shape = (kw, kh, c_in, c_out)
    pad_type = param['pad']
    if pad_type == 'CONSTANT':
        assert param['stride'] == (1, 1, 1, 1)
        X = _constant_pad(X, ker_shape)
        pad_type = 'VALID'

    kernel = scoped_variable('kernel_%s' % name, scope_name,
                             shape=ker_shape,
                             initializer=tf.contrib.layers.xavier_initializer())

    conv = tf.nn.conv2d(X, kernel, param['stride'], padding=pad_type,
                        name='conv_%s' % name)
    return conv


def deconv(X, param, name, scope_name='deconv'):
    """
    Deconvolution:
    `X` has shape `[B, W, H, C_in]`.

    `param['kernel']` is a tuple `(kw, kh, C_out, C_in)` or `(kw, kh, C_out)`.
    If `C_in` is not given, then it must be inferrable from `X.get_shape()`.

    param['stride'] is a tuple `(1, stride_w, stride_h, 1)`, defaults to `(1, 1, 1, 1)`
    param['pad'] is one of `SAME` (default), `VALID`.
    """
    assert X.get_shape().ndims == 4

    _default_value(param, 'stride', (1, 1, 1, 1))
    _default_value(param, 'pad', 'SAME')

    c_in = X.get_shape()[3].value
    ker_shape = param['kernel']

    if c_in:
        if len(ker_shape) == 3:
            kw, kh, c_out = param['kernel']
        else:
            kw, kh, c_in_, c_out = param['kernel']
            assert c_in_ == c_in, \
                "Inferred and given numbers of input_channels do not agree."

    else:
        if len(ker_shape) == 4:
            kw, kh, c_out, c_in = param['kernel']
        else:
            assert False, \
                "Number of input_channels was not given and could not be inferred."

    if param.get('bias'):
        c_in += 1
        X = tf.concat(3, [
            X, tf.ones(tf.concat(0, [tf.shape(X)[:3], [1]])),
        ], name='%s_pad1' % name,
        )

    ker_shape = (kw, kh, c_out, c_in)
    kernel = scoped_variable('kernel_%s' % name, scope_name,
                             shape=ker_shape)

    pad_type = param['pad']
    b, w, h, _ = X.get_shape().as_list()
    if w and h:
        _, sw, sh, _ = param['stride']
        w, h = w * sw, h * sh
        if pad_type == 'VALID':
            w += kw - 1
            h += kh - 1

    input_shape = tf.shape(X)
    wh_dims = input_shape[1:3] * param['stride'][1:3]
    if pad_type == 'VALID':
        wh_dims += param['kernel'][:2]
        wh_dims -= 1

    output_shape = tf.concat(0, [
        input_shape[:1],
        wh_dims,
        param['kernel'][2:3]
    ])

    deconv = tf.nn.conv2d_transpose(X, kernel,
                                    output_shape, param['stride'],
                                    name='deconv_%s' % name,
                                    padding=pad_type)
    if w and h:
        deconv.set_shape([b, w, h, c_out])

    return deconv


def gated_conv(X, param, name, scope_name='gated_conv'):
    """
    Returns tanh(conv(X, Wf)) * sigmoid(conv(X, Wg))
    """
    Xf = conv(X, param, '%s_f' % name, scope_name)
    Xg = conv(X, param, '%s_g' % name, scope_name)
    return tf.tanh(Xf) * tf.sigmoid(Xg)


def spatial_softmax(X):
    """ Spatial softmax:
        X has shape [batch, width, height, channels],
        each channel defines a spatial distribution,
        taking expectation gives pairs(x, y) of feature points.
        Output has shape[channels, 2].
    """
    _, w, h, _ = X.get_shape()
    x_map, y_map = tf.linspace(0., 1., w), tf.linspace(0., 1., h)
    x_map, y_map = tf.reshape(x_map, (1, w.value, 1)
                              ), tf.reshape(y_map, (1, h.value, 1))

    X = tf.exp(X)
    fx, fy = tf.reduce_sum(X, [1]), tf.reduce_sum(X, [2])
    fx /= tf.reduce_sum(fx, [1], keep_dims=True)
    fy /= tf.reduce_sum(fy, [1], keep_dims=True)
    fx = tf.reduce_sum(fx * x_map, [1])
    fy = tf.reduce_sum(fy * y_map, [1])

    return tf.concat(1, [fx, fy])
