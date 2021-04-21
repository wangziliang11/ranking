# Copyright 2021 The TensorFlow Ranking Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Lint as: python3
"""Keras losses in TF-Ranking."""

import tensorflow.compat.v2 as tf

from tensorflow.python.keras.utils import losses_utils
from tensorflow_ranking.python import losses_impl
from tensorflow_ranking.python.keras import utils


class RankingLossKey(object):
  """Ranking loss key strings."""
  # Names for the ranking based loss functions.
  PAIRWISE_HINGE_LOSS = 'pairwise_hinge_loss'
  PAIRWISE_LOGISTIC_LOSS = 'pairwise_logistic_loss'
  PAIRWISE_SOFT_ZERO_ONE_LOSS = 'pairwise_soft_zero_one_loss'
  SOFTMAX_LOSS = 'softmax_loss'
  UNIQUE_SOFTMAX_LOSS = 'unique_softmax_loss'
  SIGMOID_CROSS_ENTROPY_LOSS = 'sigmoid_cross_entropy_loss'
  MEAN_SQUARED_LOSS = 'mean_squared_loss'
  LIST_MLE_LOSS = 'list_mle_loss'
  APPROX_NDCG_LOSS = 'approx_ndcg_loss'
  APPROX_MRR_LOSS = 'approx_mrr_loss'
  GUMBEL_APPROX_NDCG_LOSS = 'gumbel_approx_ndcg_loss'
  # TODO: Add support for circle loss and neural sort losses.


def get(loss,
        reduction=tf.losses.Reduction.AUTO,
        lambda_weight=None,
        name=None,
        **kwargs):
  """Factory method to get a ranking loss class.

  Args:
    loss: (str) An attribute of `RankingLossKey`, defining which loss object to
      return.
    reduction: (enum)  An enum of strings indicating the loss reduction type.
      See type definition in the `tf.compat.v2.losses.Reduction`.
    lambda_weight: (losses_impl._LambdaWeight) A lambda object for ranking
      metric optimization.
    name: (optional) (str) Name of loss.
    **kwargs: Keyword arguments for the loss object.

  Returns:
    A ranking loss instance. See `_RankingLoss` signature for more details.

  Raises:
    ValueError: If loss_key is unsupported.
  """
  loss_kwargs = {'reduction': reduction, 'name': name}
  if kwargs:
    loss_kwargs.update(kwargs)

  loss_kwargs_with_lambda_weights = {'lambda_weight': lambda_weight}
  loss_kwargs_with_lambda_weights.update(loss_kwargs)

  key_to_cls = {
      RankingLossKey.SIGMOID_CROSS_ENTROPY_LOSS: SigmoidCrossEntropyLoss,
      RankingLossKey.MEAN_SQUARED_LOSS: MeanSquaredLoss,
      RankingLossKey.APPROX_NDCG_LOSS: ApproxNDCGLoss,
      RankingLossKey.APPROX_MRR_LOSS: ApproxMRRLoss,
      RankingLossKey.GUMBEL_APPROX_NDCG_LOSS: GumbelApproxNDCGLoss,
  }

  key_to_cls_with_lambda_weights = {
      RankingLossKey.LIST_MLE_LOSS: ListMLELoss,
      RankingLossKey.PAIRWISE_HINGE_LOSS: PairwiseHingeLoss,
      RankingLossKey.PAIRWISE_LOGISTIC_LOSS: PairwiseLogisticLoss,
      RankingLossKey.PAIRWISE_SOFT_ZERO_ONE_LOSS: PairwiseSoftZeroOneLoss,
      RankingLossKey.SOFTMAX_LOSS: SoftmaxLoss,
      RankingLossKey.UNIQUE_SOFTMAX_LOSS: UniqueSoftmaxLoss,
  }
  if loss in key_to_cls:
    loss_cls = key_to_cls[loss]
    loss_obj = loss_cls(**loss_kwargs)
  elif loss in key_to_cls_with_lambda_weights:
    loss_cls = key_to_cls_with_lambda_weights[loss]
    loss_obj = loss_cls(**loss_kwargs_with_lambda_weights)
  else:
    raise ValueError('unsupported loss: {}'.format(loss))

  return loss_obj


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class DCGLambdaWeight(losses_impl.DCGLambdaWeight):
  """Keras serializable class for DCG."""

  def __init__(self,
               topn=None,
               gain_fn=None,
               rank_discount_fn=None,
               normalized=False,
               smooth_fraction=0.,
               **kwargs):
    gain_fn = gain_fn or utils.identity
    rank_discount_fn = rank_discount_fn or utils.inverse
    super().__init__(topn, gain_fn, rank_discount_fn, normalized,
                     smooth_fraction)

  def get_config(self):
    return {
        'topn': self._topn,
        'gain_fn': self._gain_fn,
        'rank_discount_fn': self._rank_discount_fn,
        'normalized': self._normalized,
        'smooth_fraction': self._smooth_fraction,
    }


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class NDCGLambdaWeight(DCGLambdaWeight):
  """Keras serializable class for NDCG."""

  def __init__(self,
               topn=None,
               gain_fn=None,
               rank_discount_fn=None,
               smooth_fraction=0.,
               **kwargs):
    super().__init__(
        topn,
        gain_fn or utils.pow_minus_1,
        rank_discount_fn or utils.log2_inverse,
        normalized=True,
        smooth_fraction=smooth_fraction)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class PrecisionLambdaWeight(losses_impl.PrecisionLambdaWeight):
  """Keras serializable class for Precision."""

  def __init__(self, topn=None, positive_fn=None, **kwargs):
    positive_fn = positive_fn or utils.is_greater_equal_1
    super().__init__(topn, positive_fn)

  def get_config(self):
    return {
        'topn': self._topn,
        'positive_fn': self._positive_fn,
    }


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class ListMLELambdaWeight(losses_impl.ListMLELambdaWeight):

  def __init__(self, rank_discount_fn, **kwargs):
    super().__init__(rank_discount_fn)

  def get_config(self):
    return {
        'rank_discount_fn': self._rank_discount_fn,
    }


class _RankingLoss(tf.keras.losses.Loss):
  """Base class for all ranking losses.

  Please see tf.keras.losses.Loss for more information about such a class and
  https://www.tensorflow.org/tutorials/distribute/custom_training on how to do
  customized training.
  """

  def __init__(self, reduction=tf.losses.Reduction.AUTO, name=None):
    super().__init__(reduction, name)
    # An instance of loss in `losses_impl`. Overwrite this in subclasses.
    self._loss = None

  def __call__(self, y_true, y_pred, sample_weight=None):
    """See tf.keras.losses.Loss."""
    if self._loss is None:
      raise ValueError('self._loss is not defined. Please use a subclass.')
    sample_weight = self._loss.normalize_weights(y_true, sample_weight)
    return super().__call__(y_true, y_pred, sample_weight)

  def call(self, y_true, y_pred):
    """See tf.keras.losses.Loss."""
    y_pred = self._loss.get_logits(y_pred)
    losses, weights = self._loss.compute_unreduced_loss(
        labels=y_true, logits=y_pred)
    return tf.multiply(losses, weights)


class _PairwiseLoss(_RankingLoss):
  """Base class for pairwise ranking losses."""

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=1.0,
               **kwargs):
    super().__init__(reduction, name)
    self._lambda_weight = lambda_weight
    self._temperature = temperature

  def get_config(self):
    config = super().get_config()
    config.update({
        'lambda_weight':
            tf.keras.utils.serialize_keras_object(self._lambda_weight),
        'temperature':
            self._temperature,
    })
    return config

  @classmethod
  def from_config(cls, config, custom_objects=None):
    config = config.copy()
    config.update({
        'lambda_weight':
            tf.keras.utils.deserialize_keras_object(config['lambda_weight']),
    })
    return cls(**config)

  def call(self, y_true, y_pred):
    """See _RankingLoss."""
    losses, weights = self._loss.compute_unreduced_loss(
        labels=y_true, logits=y_pred)
    losses = tf.multiply(losses, weights)
    # [batch_size, list_size, list_size]
    losses.get_shape().assert_has_rank(3)
    # Reduce the loss along the last dim so that weights ([batch_size, 1] or
    # [batch_size, list_size] can be applied in __call__.
    return tf.reduce_sum(losses, axis=2)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class PairwiseHingeLoss(_PairwiseLoss):
  r"""Pairwise hinge loss.

  $$
  \mathcal{L}(\{y\}, \{s\}) =
  \sum_{i, j} I_{y_i > y_j} \max(0, 1 - (s_i - s_j))
  $$
  """

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=1.0,
               ragged=False):
    """Pairwise hinge loss.

    Args:
      reduction: (Optional) The `tf.keras.losses.Reduction` to use (see
        `tf.keras.losses.Loss`).
      name: (Optional) The name for the op.
      lambda_weight: (Optional) A lambdaweight to apply to the loss. Can be one
        of `tfr.keras.losses.DCGLambdaWeight`,
        `tfr.keras.losses.NDCGLambdaWeight`, or,
        `tfr.keras.losses.PrecisionLambdaWeight`.
      temperature: (Optional) The temperature to use for scaling the logits.
      ragged: (Optional) If True, this loss will accept ragged tensors. If
        False, this loss will accept dense tensors.
    """
    super().__init__(reduction, name, lambda_weight, temperature)
    self._loss = losses_impl.PairwiseHingeLoss(
        name='{}_impl'.format(name) if name else None,
        lambda_weight=lambda_weight,
        temperature=temperature,
        ragged=ragged)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class PairwiseLogisticLoss(_PairwiseLoss):
  r"""Pairwise logistic loss.

  $$
  \mathcal{L}(\{y\}, \{s\}) =
  \sum_{i, j} I_{y_i > y_j} \log(1 + \exp(-(s_i - s_j)))
  $$
  """

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=1.0,
               ragged=False):
    """Pairwise logistic loss.

    Args:
      reduction: (Optional) The `tf.keras.losses.Reduction` to use (see
        `tf.keras.losses.Loss`).
      name: (Optional) The name for the op.
      lambda_weight: (Optional) A lambdaweight to apply to the loss. Can be one
        of `tfr.keras.losses.DCGLambdaWeight`,
        `tfr.keras.losses.NDCGLambdaWeight`, or,
        `tfr.keras.losses.PrecisionLambdaWeight`.
      temperature: (Optional) The temperature to use for scaling the logits.
      ragged: (Optional) If True, this loss will accept ragged tensors. If
        False, this loss will accept dense tensors.
    """
    super().__init__(reduction, name, lambda_weight, temperature)
    self._loss = losses_impl.PairwiseLogisticLoss(
        name='{}_impl'.format(name) if name else None,
        lambda_weight=lambda_weight,
        temperature=temperature,
        ragged=ragged)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class PairwiseSoftZeroOneLoss(_PairwiseLoss):
  r"""Pairwise soft zero one loss.

  $$
  \mathcal{L}(\{y\}, \{s\}) =
  \sum_{i, j} I_{y_i > y_j} (1 - \text{sigmoid}(s_i - s_j))
  $$
  """

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=1.0,
               ragged=False):
    """Pairwise soft zero one loss.

    Args:
      reduction: (Optional) The `tf.keras.losses.Reduction` to use (see
        `tf.keras.losses.Loss`).
      name: (Optional) The name for the op.
      lambda_weight: (Optional) A lambdaweight to apply to the loss. Can be one
        of `tfr.keras.losses.DCGLambdaWeight`,
        `tfr.keras.losses.NDCGLambdaWeight`, or,
        `tfr.keras.losses.PrecisionLambdaWeight`.
      temperature: (Optional) The temperature to use for scaling the logits.
      ragged: (Optional) If True, this loss will accept ragged tensors. If
        False, this loss will accept dense tensors.
    """
    super().__init__(reduction, name, lambda_weight, temperature)
    self._loss = losses_impl.PairwiseSoftZeroOneLoss(
        name='{}_impl'.format(name) if name else None,
        lambda_weight=lambda_weight,
        temperature=temperature,
        ragged=ragged)


class _ListwiseLoss(_RankingLoss):
  """Base class for listwise ranking losses."""

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=1.0,
               **kwargs):
    super().__init__(reduction, name)
    self._lambda_weight = lambda_weight
    self._temperature = temperature

  def get_config(self):
    config = super().get_config()
    config.update({
        'lambda_weight':
            tf.keras.utils.serialize_keras_object(self._lambda_weight),
        'temperature':
            self._temperature,
    })
    return config

  @classmethod
  def from_config(cls, config, custom_objects=None):
    config = config.copy()
    config.update({
        'lambda_weight':
            tf.keras.utils.deserialize_keras_object(config['lambda_weight']),
    })
    return cls(**config)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class SoftmaxLoss(_ListwiseLoss):
  r"""Softmax cross-entropy loss.

  $$
  \mathcal{L}(\{y\}, \{s\}) =
  - \sum_i \frac{y_i}{\sum_j y_j} \cdot \log(\text{softmax}(s_i))
  $$
  """

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=1.0,
               ragged=False):
    """Softmax cross-entropy loss.

    Args:
      reduction: (Optional) The `tf.keras.losses.Reduction` to use (see
        `tf.keras.losses.Loss`).
      name: (Optional) The name for the op.
      lambda_weight: (Optional) A lambdaweight to apply to the loss. Can be one
        of `tfr.keras.losses.DCGLambdaWeight`,
        `tfr.keras.losses.NDCGLambdaWeight`, or,
        `tfr.keras.losses.PrecisionLambdaWeight`.
      temperature: (Optional) The temperature to use for scaling the logits.
      ragged: (Optional) If True, this loss will accept ragged tensors. If
        False, this loss will accept dense tensors.
    """
    super().__init__(reduction, name, lambda_weight, temperature)
    self._loss = losses_impl.SoftmaxLoss(
        name='{}_impl'.format(name) if name else None,
        lambda_weight=lambda_weight,
        temperature=temperature,
        ragged=ragged)

  def __call__(self, y_true, y_pred, sample_weight=None):
    """See _RankingLoss."""
    losses, sample_weight = self._loss.compute_per_list(
        y_true, y_pred, sample_weight)
    return losses_utils.compute_weighted_loss(
        losses, sample_weight, reduction=self._get_reduction())


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class UniqueSoftmaxLoss(_ListwiseLoss):
  """For unique softmax cross entropy loss."""

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=1.0,
               ragged=False):
    super().__init__(reduction, name, lambda_weight, temperature)
    self._loss = losses_impl.UniqueSoftmaxLoss(
        name='{}_impl'.format(name) if name else None,
        lambda_weight=lambda_weight,
        temperature=temperature,
        ragged=ragged)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class ListMLELoss(_ListwiseLoss):
  r"""ListMLE loss.

  $$
  \mathcal{L}(\{y\}, \{s\}) = - \log(P(\pi_y | s))
  $$

  where $$P(\pi_y | s)$$ is the plackett-luce probability of a permutation
  $$\pi_y$$ conditioned on scores $$s$$. Here $$\pi_y$$ represents a permutation
  of items ordered by the relevance labels $$y$$ where ties are broken randomly.

  NOTE: Since tie breaks happen randomly, this loss is stochastic and may return
  different values for identical inputs.

  """

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=1.0,
               ragged=False):
    """ListMLE loss.

    Args:
      reduction: (Optional) The `tf.keras.losses.Reduction` to use (see
        `tf.keras.losses.Loss`).
      name: (Optional) The name for the op.
      lambda_weight: (Optional) A lambdaweight to apply to the loss. Can be one
        of `tfr.keras.losses.DCGLambdaWeight`,
        `tfr.keras.losses.NDCGLambdaWeight`,
        `tfr.keras.losses.PrecisionLambdaWeight`, or,
        `tfr.keras.losses.ListMLELambdaWeight`.
      temperature: (Optional) The temperature to use for scaling the logits.
      ragged: (Optional) If True, this loss will accept ragged tensors. If
        False, this loss will accept dense tensors.
    """
    super().__init__(reduction, name, lambda_weight, temperature)
    self._loss = losses_impl.ListMLELoss(
        name='{}_impl'.format(name) if name else None,
        lambda_weight=lambda_weight,
        temperature=temperature,
        ragged=ragged)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class ApproxMRRLoss(_ListwiseLoss):
  """For approximate MRR loss."""

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=0.1,
               ragged=False):
    super().__init__(reduction, name, lambda_weight, temperature)
    self._loss = losses_impl.ApproxMRRLoss(
        name='{}_impl'.format(name) if name else None,
        lambda_weight=lambda_weight,
        temperature=temperature,
        ragged=ragged)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class ApproxNDCGLoss(_ListwiseLoss):
  """For approximate NDCG loss."""

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=0.1,
               ragged=False):
    super().__init__(reduction, name, lambda_weight, temperature)
    self._loss = losses_impl.ApproxNDCGLoss(
        name='{}_impl'.format(name) if name else None,
        lambda_weight=lambda_weight,
        temperature=temperature,
        ragged=ragged)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class GumbelApproxNDCGLoss(ApproxNDCGLoss):
  """For Gumbel approximate NDCG loss."""

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               lambda_weight=None,
               temperature=0.1,
               sample_size=8,
               gumbel_temperature=1.0,
               seed=None):
    super().__init__(reduction, name, lambda_weight, temperature=temperature)
    self._sample_size = sample_size
    self._gumbel_temperature = gumbel_temperature
    self._seed = seed

    self._gumbel_sampler = losses_impl.GumbelSampler(
        name=name,
        sample_size=sample_size,
        temperature=gumbel_temperature,
        seed=seed)

  def get_config(self):
    config = super().get_config()
    config.update({
        'sample_size': self._sample_size,
        'gumbel_temperature': self._gumbel_temperature,
        'seed': self._seed,
    })
    return config

  def __call__(self, y_true, y_pred, sample_weight=None):
    """See _RankingLoss."""
    # For Gumbel approx NDCG, the logits are sampled from Gumbel distribution
    # to sort the documents.
    # TODO: Add ragged support for sampler.
    gbl_labels, gbl_logits, gbl_weights = self._gumbel_sampler.sample(
        y_true, y_pred, weights=sample_weight)
    return super().__call__(gbl_labels, gbl_logits, gbl_weights)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class ClickEMLoss(_RankingLoss):
  """For click EM loss."""

  def __init__(self,
               reduction=tf.losses.Reduction.AUTO,
               name=None,
               exam_loss_weight=1.0,
               rel_loss_weight=1.0,
               ragged=False):
    super().__init__(reduction, name)
    self._exam_loss_weight = exam_loss_weight
    self._rel_loss_weight = rel_loss_weight
    self._loss = losses_impl.ClickEMLoss(
        name='{}_impl'.format(name) if name else None,
        exam_loss_weight=self._exam_loss_weight,
        rel_loss_weight=self._rel_loss_weight,
        ragged=ragged)

  def get_config(self):
    config = super().get_config()
    config.update({
        'exam_loss_weight': self._exam_loss_weight,
        'rel_loss_weight': self._rel_loss_weight,
    })
    return config


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class SigmoidCrossEntropyLoss(_RankingLoss):
  """For sigmoid cross-entropy loss."""

  def __init__(self, reduction=tf.losses.Reduction.AUTO, name=None,
               ragged=False):
    super().__init__(reduction, name)
    self._loss = losses_impl.SigmoidCrossEntropyLoss(
        name='{}_impl'.format(name) if name else None,
        ragged=ragged)


@tf.keras.utils.register_keras_serializable(package='tensorflow_ranking')
class MeanSquaredLoss(_RankingLoss):
  r"""Mean squared loss.

  $$
  \mathcal{L}(\{y\}, \{s\}) = \sum_i (y_i - s_i)^{2}
  $$
  """

  def __init__(self, reduction=tf.losses.Reduction.AUTO, name=None,
               ragged=False):
    """Mean squared loss.

    Args:
      reduction: (Optional) The `tf.keras.losses.Reduction` to use (see
        `tf.keras.losses.Loss`).
      name: (Optional) The name for the op.
      ragged: (Optional) If True, this loss will accept ragged tensors. If
        False, this loss will accept dense tensors.
    """
    super().__init__(reduction, name)
    self._loss = losses_impl.MeanSquaredLoss(
        name='{}_impl'.format(name) if name else None, ragged=ragged)
