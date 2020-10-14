from sentence_transformers import SentenceTransformer
import plotly.express as px
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.preprocessing import normalize
import numpy as np
from code import utils
import nltk, re, time, umap
from hdbscan import HDBSCAN
from sentence_transformers import models

from transformers import AutoModel, AutoTokenizer
from torch import nn

tokenizer = AutoTokenizer.from_pretrained("dbmdz/bert-base-german-cased")

word_embedding_model = models.Transformer(
    'T-Systems-onsite/bert-german-dbmdz-uncased-sentence-stsb')

# Apply mean pooling to get one fixed sized sentence vector
pooling_model = models.Pooling(word_embedding_model.get_word_embedding_dimension(),
                               pooling_mode_mean_tokens=True,
                               pooling_mode_cls_token=False,
                               pooling_mode_max_tokens=True)

# join BERT model and pooling to get the sentence transformer
model = SentenceTransformer(modules=[word_embedding_model, pooling_model])


def cluster_and_reduce(embeddings, one_day=False, n_components_clustering=384, **kwargs):
    st = time.time()
    umap_data = umap.UMAP(n_neighbors=50, n_components=3, metric='cosine').fit_transform(embeddings)
    print(">> Reducing dimensionality from {} to {} ...".format(embeddings.shape[1], str(n_components_clustering)))
    if len(embeddings) > n_components_clustering:
        umap_embeddings = umap.UMAP(n_neighbors=15,
                                    n_components=n_components_clustering,
                                    metric='cosine').fit_transform(embeddings)
    else:
        umap_embeddings = umap.UMAP(n_neighbors=15,
                                    n_components=n_components_clustering,
                                    metric='cosine', init="random").fit_transform(embeddings)

    params = {"min_cluster_size": 6, "alpha": 0.88, "cluster_selection_epsilon": 0.11
        , "metric": 'euclidean', "min_samples": 3,
              "cluster_selection_method": 'eom', "approx_min_span_tree": True}

    if one_day:
        params["min_cluster_size"] = 3

    for (k, v) in kwargs.items():
        params[k] = v

    print(">> Clustering...")
    clusters = HDBSCAN(**params).fit_predict(umap_embeddings)
    print(">> --- Done in {:.1f} seconds ---".format(time.time() - st))

    return umap_data, clusters


def scatter_plot(result):
    result["labels"] = result.labels.apply(str)
    fig = px.scatter(result, x="x", y="y", hover_name="headline", hover_data=["created_at"], color="labels",
                     opacity=0.8)
    fig.update_traces(marker=dict(size=9,
                                  line=dict(width=0.15,
                                            color='DarkSlateGrey')),
                      selector=dict(mode='markers'))
    fig["layout"].pop("updatemenus")
    fig.update_layout(
        height=1000)
    fig.show()


def c_tf_idf(documents, m, ngram_range=(1, 1), remove_stop_words=True):
    if remove_stop_words:
        def remove_stop_words(doc):
            for sword in utils.STOPWORDS:
                doc = doc.replace(sword, "")
                return doc

        documents = np.array(list(map(remove_stop_words, documents)))

    count = CountVectorizer(ngram_range=ngram_range).fit(documents)
    t = count.transform(documents).toarray()
    w = t.sum(axis=1)
    tf = np.divide(t.T, w)
    sum_t = t.sum(axis=0)
    idf = np.log(np.divide(m, sum_t)).reshape(-1, 1)
    tf_idf = np.multiply(tf, idf)

    return tf_idf, count


def extract_top_n_words_per_topic(tf_idf, count, docs_per_topic, n=20):
    words = count.get_feature_names()
    labels = list(docs_per_topic.Topic)
    tf_idf_transposed = tf_idf.T
    indices = tf_idf_transposed.argsort()[:, -n:]
    top_n_words = {label: [(words[j], tf_idf_transposed[i][j]) for j in indices[i]][::-1] for i, label in
                   enumerate(labels)}
    return top_n_words


def extract_topic_sizes(df):
    topic_sizes = (df.groupby(['Topic'])
                   .Doc
                   .count()
                   .reset_index()
                   .rename({"Topic": "Topic", "Doc": "Size"}, axis='columns')
                   .sort_values("Size", ascending=False))
    return topic_sizes