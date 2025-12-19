import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  Trash2,
  Search,
  FileText,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { filesApi } from '../api';

function FilePreview() {
  const { fileId } = useParams();
  const navigate = useNavigate();
  const [fileInfo, setFileInfo] = useState(null);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadData();
  }, [fileId]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [info, preview] = await Promise.all([
        filesApi.get(fileId),
        filesApi.preview(fileId, 500),
      ]);
      setFileInfo(info);
      setProducts(preview.products || []);
    } catch (err) {
      setError('Error al cargar datos del archivo');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`¿Estás seguro de eliminar "${fileInfo?.filename}"?\n\nEsto eliminará el archivo y todos los productos indexados.`)) {
      return;
    }

    setDeleting(true);
    try {
      await filesApi.delete(fileId);
      navigate('/files');
    } catch (err) {
      alert('Error al eliminar archivo');
      setDeleting(false);
    }
  };

  const handleDownload = async () => {
    try {
      const data = await filesApi.getDownloadUrl(fileId);
      window.open(data.download_url, '_blank');
    } catch (err) {
      alert('Error al obtener URL de descarga');
    }
  };

  const filteredProducts = products.filter((product) =>
    product.nombre?.toLowerCase().includes(search.toLowerCase()) ||
    product.codigo?.toLowerCase().includes(search.toLowerCase()) ||
    product.tienda_id?.toString().includes(search)
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/files')}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-800"
        >
          <ArrowLeft className="w-4 h-4" />
          Volver
        </button>
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/files')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-800 truncate max-w-md">
              {fileInfo?.filename}
            </h1>
            <p className="text-sm text-gray-500">
              {fileInfo?.products_count?.toLocaleString()} productos indexados
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownload}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <Download className="w-4 h-4" />
            Descargar
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            {deleting ? (
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
            Eliminar
          </button>
        </div>
      </div>

      {/* File info */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <p className="text-sm text-gray-500">ID del archivo</p>
            <p className="font-mono text-sm text-gray-800">{fileInfo?.file_id}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Tamaño</p>
            <p className="font-medium text-gray-800">
              {fileInfo?.size ? `${(fileInfo.size / 1024).toFixed(2)} KB` : 'N/A'}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Tipo</p>
            <p className="font-medium text-gray-800">{fileInfo?.content_type}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Estado</p>
            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
              fileInfo?.status === 'indexed'
                ? 'bg-green-100 text-green-700'
                : 'bg-yellow-100 text-yellow-700'
            }`}>
              {fileInfo?.status === 'indexed' ? 'Indexado' : fileInfo?.status}
            </span>
          </div>
        </div>
      </div>

      {/* Products table */}
      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        <div className="p-4 border-b flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h2 className="font-semibold text-gray-800">
            Vista previa de productos ({filteredProducts.length} de {products.length})
          </h2>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Buscar producto..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 w-64"
              />
            </div>
            <button
              onClick={loadData}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <RefreshCw className="w-5 h-5 text-gray-600" />
            </button>
          </div>
        </div>

        {filteredProducts.length === 0 ? (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">No se encontraron productos</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    #
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Nombre
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Precio
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Tienda
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Código
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Categoría
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {filteredProducts.slice(0, 100).map((product, index) => (
                  <tr key={index} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {index + 1}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-800 truncate max-w-xs">
                        {product.nombre || '-'}
                      </p>
                      {product.presentacion && (
                        <p className="text-xs text-gray-500">{product.presentacion}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-800">
                      {product.precio ? `$${product.precio.toFixed(2)}` : '-'}
                    </td>
                    <td className="px-4 py-3">
                      {product.tienda_id ? (
                        <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-sm">
                          {product.tienda_id}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 font-mono">
                      {product.codigo || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {product.categoria || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {filteredProducts.length > 100 && (
          <div className="p-4 bg-gray-50 text-center text-sm text-gray-500">
            Mostrando los primeros 100 de {filteredProducts.length} productos
          </div>
        )}
      </div>
    </div>
  );
}

export default FilePreview;
