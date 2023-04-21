""" Moss model configuration"""

from transformers.utils import logging
from transformers.configuration_utils import PretrainedConfig


logger = logging.get_logger(__name__)


class MossConfig(PretrainedConfig):
    r"""
    This is the configuration class to store the configuration of a [`MossModel`]. It is used to instantiate a
    Moss model according to the specified arguments, defining the model architecture. Instantiating a configuration
    with the defaults will yield a similar configuration to that of the Moss
    [fnlp/moss-moon-003-base](https://huggingface.co/fnlp/moss-moon-003-base) architecture. Configuration objects
    inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the documentation from
    [`PretrainedConfig`] for more information.

    Args:
        vocab_size (`int`, *optional*, defaults to 107008):
            Vocabulary size of the Moss model. Defines the number of different tokens that can be represented by the
            `inputs_ids` passed when calling [`MossModel`].
        n_positions (`int`, *optional*, defaults to 2048):
            The maximum sequence length that this model might ever be used with. Typically set this to something large
            just in case (e.g., 512 or 1024 or 2048).
        n_embd (`int`, *optional*, defaults to 4096):
            Dimensionality of the embeddings and hidden states.
        n_layer (`int`, *optional*, defaults to 28):
            Number of hidden layers in the Transformer encoder.
        n_head (`int`, *optional*, defaults to 16):
            Number of attention heads for each attention layer in the Transformer encoder.
        rotary_dim (`int`, *optional*, defaults to 64):
            Number of dimensions in the embedding that Rotary Position Embedding is applied to.
        n_inner (`int`, *optional*, defaults to None):
            Dimensionality of the inner feed-forward layers. `None` will set it to 4 times n_embd
        activation_function (`str`, *optional*, defaults to `"gelu_new"`):
            Activation function, to be selected in the list `["relu", "silu", "gelu", "tanh", "gelu_new"]`.
        resid_pdrop (`float`, *optional*, defaults to 0.1):
            The dropout probability for all fully connected layers in the embeddings, encoder, and pooler.
        embd_pdrop (`int`, *optional*, defaults to 0.1):
            The dropout ratio for the embeddings.
        attn_pdrop (`float`, *optional*, defaults to 0.1):
            The dropout ratio for the attention.
        layer_norm_epsilon (`float`, *optional*, defaults to 1e-5):
            The epsilon to use in the layer normalization layers.
        initializer_range (`float`, *optional*, defaults to 0.02):
            The standard deviation of the truncated_normal_initializer for initializing all weight matrices.
        use_cache (`bool`, *optional*, defaults to `True`):
            Whether or not the model should return the last key/values attentions (not used by all models).

    Example:

    ```python
    >>> from modeling_moss import MossModel
    >>> from configuration_moss import MossConfig

    >>> # Initializing a moss-moon-003-base configuration
    >>> configuration = MossConfig()

    >>> # Initializing a model (with random weights) from the configuration
    >>> model = MossModel(configuration)

    >>> # Accessing the model configuration
    >>> configuration = model.config
    ```"""

    model_type = "moss"
    attribute_map = {
        "max_position_embeddings": "n_positions",
        "hidden_size": "n_embd",
        "num_attention_heads": "n_head",
        "num_hidden_layers": "n_layer",
    }

    def __init__(
        self,
        vocab_size=107008,
        n_positions=2048,
        n_ctx=2048,
        n_embd=4096,
        n_layer=28,
        n_head=16,
        rotary_dim=64,
        n_inner=None,
        activation_function="gelu_new",
        resid_pdrop=0.0,
        embd_pdrop=0.0,
        attn_pdrop=0.0,
        layer_norm_epsilon=1e-5,
        initializer_range=0.02,
        use_cache=True,
        bos_token_id=106028,
        eos_token_id=106068,
        tie_word_embeddings=False,
        **kwargs,
    ):
        self.vocab_size = vocab_size
        self.n_ctx = n_ctx
        self.n_positions = n_positions
        self.n_embd = n_embd
        self.n_layer = n_layer
        self.n_head = n_head
        self.n_inner = n_inner
        self.rotary_dim = rotary_dim
        self.activation_function = activation_function
        self.resid_pdrop = resid_pdrop
        self.embd_pdrop = embd_pdrop
        self.attn_pdrop = attn_pdrop
        self.layer_norm_epsilon = layer_norm_epsilon
        self.initializer_range = initializer_range
        self.use_cache = use_cache

        self.bos_token_id = bos_token_id
        self.eos_token_id = eos_token_id

        super().__init__(
            bos_token_id=bos_token_id, eos_token_id=eos_token_id, tie_word_embeddings=tie_word_embeddings, **kwargs
        )
