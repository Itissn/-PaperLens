from paperlens.embeddings import Embedder
from paperlens.paths import CACHE

def main():
    encoder = Embedder(CACHE / 'embeddings')
    vector = encoder.query('research paper')
    if vector.shape != (384,):
        raise RuntimeError('Unexpected search model dimensions.')
    print('Search model verified: 384 dimensions.')

if __name__ == '__main__':
    main()
