import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Upload,
  FileText,
  X,
  CheckCircle,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { filesApi } from '../api';

function FileUpload({ onSuccess }) {
  const [file, setFile] = useState(null);
  const [tiendaId, setTiendaId] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const navigate = useNavigate();

  const supportedFormats = [
    { ext: 'CSV', desc: 'Archivos separados por comas' },
    { ext: 'XLSX/XLS', desc: 'Microsoft Excel' },
    { ext: 'PDF', desc: 'Documentos PDF' },
    { ext: 'TXT', desc: 'Archivos de texto' },
    { ext: 'DOCX/DOC', desc: 'Microsoft Word' },
    { ext: 'PNG/JPG', desc: 'Imágenes' },
  ];

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setResult(null);
      setError(null);
    }
  }, []);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setResult(null);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setProgress(0);
    setError(null);
    setResult(null);

    try {
      const data = await filesApi.upload(file, tiendaId || null, setProgress);
      setResult(data);
      if (onSuccess) onSuccess();
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al subir archivo');
    } finally {
      setUploading(false);
    }
  };

  const resetForm = () => {
    setFile(null);
    setTiendaId('');
    setResult(null);
    setError(null);
    setProgress(0);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Subir Archivo</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Upload form */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl shadow-sm p-6 space-y-6">
            {/* Dropzone */}
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
                dragActive
                  ? 'border-primary-500 bg-primary-50'
                  : file
                  ? 'border-green-500 bg-green-50'
                  : 'border-gray-300 hover:border-gray-400'
              }`}
            >
              <input
                type="file"
                onChange={handleFileChange}
                accept=".csv,.xlsx,.xls,.pdf,.txt,.docx,.doc,.png,.jpg,.jpeg"
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                disabled={uploading}
              />

              {file ? (
                <div className="space-y-3">
                  <FileText className="w-12 h-12 text-green-500 mx-auto" />
                  <div>
                    <p className="font-medium text-gray-800">{file.name}</p>
                    <p className="text-sm text-gray-500">
                      {(file.size / 1024).toFixed(2)} KB
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      resetForm();
                    }}
                    className="text-sm text-red-600 hover:text-red-700"
                  >
                    Cambiar archivo
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  <Upload className="w-12 h-12 text-gray-400 mx-auto" />
                  <div>
                    <p className="font-medium text-gray-800">
                      Arrastra un archivo aquí
                    </p>
                    <p className="text-sm text-gray-500">
                      o haz clic para seleccionar
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Store ID */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                ID de Tienda (opcional)
              </label>
              <input
                type="text"
                value={tiendaId}
                onChange={(e) => setTiendaId(e.target.value)}
                placeholder="Ej: 810"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                disabled={uploading}
              />
              <p className="mt-1 text-sm text-gray-500">
                Si los productos no tienen tienda asignada, se usará este valor.
              </p>
            </div>

            {/* Progress */}
            {uploading && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Subiendo...</span>
                  <span className="font-medium text-primary-600">{progress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-primary-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                <span className="text-red-700">{error}</span>
              </div>
            )}

            {/* Success */}
            {result && (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg space-y-3">
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-5 h-5 text-green-500" />
                  <span className="font-medium text-green-700">
                    ¡Archivo procesado exitosamente!
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Productos extraídos:</span>
                    <span className="ml-2 font-medium">{result.products_extracted}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Productos indexados:</span>
                    <span className="ml-2 font-medium">{result.products_indexed}</span>
                  </div>
                  {result.errors > 0 && (
                    <div className="col-span-2 text-yellow-700">
                      ⚠️ {result.errors} productos con errores
                    </div>
                  )}
                </div>
                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => navigate(`/files/${result.file_id}`)}
                    className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
                  >
                    Ver productos
                  </button>
                  <button
                    onClick={resetForm}
                    className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Subir otro
                  </button>
                </div>
              </div>
            )}

            {/* Upload button */}
            {!result && (
              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="w-full py-3 px-4 bg-primary-600 hover:bg-primary-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {uploading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Procesando...</span>
                  </>
                ) : (
                  <>
                    <Upload className="w-5 h-5" />
                    <span>Subir y procesar</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Help sidebar */}
        <div className="space-y-6">
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h3 className="font-semibold text-gray-800 mb-4">Formatos soportados</h3>
            <div className="space-y-3">
              {supportedFormats.map((format) => (
                <div key={format.ext} className="flex items-start gap-3">
                  <div className="w-2 h-2 bg-primary-500 rounded-full mt-2"></div>
                  <div>
                    <p className="font-medium text-gray-800">{format.ext}</p>
                    <p className="text-sm text-gray-500">{format.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-blue-50 rounded-xl p-6">
            <h3 className="font-semibold text-blue-800 mb-2">💡 Consejos</h3>
            <ul className="text-sm text-blue-700 space-y-2">
              <li>• La primera fila debe contener los nombres de las columnas</li>
              <li>• Columnas requeridas: nombre del producto</li>
              <li>• Columnas opcionales: precio, tienda_id, codigo, categoria</li>
              <li>• Los nombres de productos se convertirán a mayúsculas</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export default FileUpload;
