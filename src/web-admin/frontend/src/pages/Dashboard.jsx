import React, { useState, useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderOpen,
  Upload,
  LogOut,
  Database,
  FileText,
  Menu,
  X,
} from 'lucide-react';
import { statsApi } from '../api';
import FileList from '../components/FileList';
import FileUpload from '../components/FileUpload';
import FilePreview from '../components/FilePreview';

function Dashboard({ onLogout }) {
  const [stats, setStats] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const data = await statsApi.get();
      setStats(data);
    } catch (err) {
      console.error('Error loading stats:', err);
    }
  };

  const navigation = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'Archivos', href: '/files', icon: FolderOpen },
    { name: 'Subir Archivo', href: '/upload', icon: Upload },
  ];

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Mobile menu button */}
      <div className="lg:hidden fixed top-4 left-4 z-50">
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 bg-white rounded-lg shadow-lg"
        >
          {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-white shadow-xl transform transition-transform duration-300 ease-in-out ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0`}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center gap-3 px-6 py-5 border-b">
            <span className="text-3xl">🛒</span>
            <div>
              <h1 className="font-bold text-gray-800">A-Patricia</h1>
              <p className="text-xs text-gray-500">Admin Panel</p>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-4 py-6 space-y-1">
            {navigation.map((item) => (
              <a
                key={item.name}
                href={item.href}
                className="flex items-center gap-3 px-4 py-3 text-gray-700 rounded-lg hover:bg-primary-50 hover:text-primary-700 transition-colors"
              >
                <item.icon className="w-5 h-5" />
                <span>{item.name}</span>
              </a>
            ))}
          </nav>

          {/* Stats */}
          {stats && (
            <div className="px-4 py-4 border-t">
              <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">Productos</span>
                  <span className="font-semibold text-primary-600">
                    {stats.total_products?.toLocaleString() || 0}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">Archivos</span>
                  <span className="font-semibold text-primary-600">
                    {stats.total_files || 0}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-green-500" />
                  <span className="text-xs text-gray-500">Qdrant: {stats.qdrant_status}</span>
                </div>
              </div>
            </div>
          )}

          {/* Logout */}
          <div className="px-4 py-4 border-t">
            <button
              onClick={onLogout}
              className="flex items-center gap-3 w-full px-4 py-3 text-gray-700 rounded-lg hover:bg-red-50 hover:text-red-700 transition-colors"
            >
              <LogOut className="w-5 h-5" />
              <span>Cerrar sesión</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="lg:ml-64 min-h-screen">
        <div className="p-6 lg:p-8">
          <Routes>
            <Route path="/" element={<DashboardHome stats={stats} onRefresh={loadStats} />} />
            <Route path="/files" element={<FileList onRefresh={loadStats} />} />
            <Route path="/upload" element={<FileUpload onSuccess={loadStats} />} />
            <Route path="/files/:fileId" element={<FilePreview />} />
          </Routes>
        </div>
      </main>

      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}
    </div>
  );
}

function DashboardHome({ stats, onRefresh }) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
        <button
          onClick={onRefresh}
          className="px-4 py-2 text-sm bg-white rounded-lg shadow hover:bg-gray-50 transition-colors"
        >
          Actualizar
        </button>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-primary-100 rounded-lg">
              <Database className="w-6 h-6 text-primary-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">Total Productos</p>
              <p className="text-2xl font-bold text-gray-800">
                {stats?.total_products?.toLocaleString() || 0}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-green-100 rounded-lg">
              <FileText className="w-6 h-6 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-gray-500">Archivos Cargados</p>
              <p className="text-2xl font-bold text-gray-800">
                {stats?.total_files || 0}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="flex items-center gap-4">
            <div className={`p-3 rounded-lg ${
              stats?.qdrant_status === 'green' ? 'bg-green-100' : 'bg-yellow-100'
            }`}>
              <Database className={`w-6 h-6 ${
                stats?.qdrant_status === 'green' ? 'text-green-600' : 'text-yellow-600'
              }`} />
            </div>
            <div>
              <p className="text-sm text-gray-500">Estado Qdrant</p>
              <p className="text-2xl font-bold text-gray-800 capitalize">
                {stats?.qdrant_status || 'Desconocido'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Quick actions */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Acciones Rápidas</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <a
            href="/upload"
            className="flex items-center gap-4 p-4 border-2 border-dashed border-gray-200 rounded-lg hover:border-primary-500 hover:bg-primary-50 transition-colors"
          >
            <Upload className="w-8 h-8 text-primary-600" />
            <div>
              <p className="font-medium text-gray-800">Subir Archivo</p>
              <p className="text-sm text-gray-500">CSV, Excel, PDF, TXT, DOCX</p>
            </div>
          </a>
          <a
            href="/files"
            className="flex items-center gap-4 p-4 border-2 border-dashed border-gray-200 rounded-lg hover:border-primary-500 hover:bg-primary-50 transition-colors"
          >
            <FolderOpen className="w-8 h-8 text-primary-600" />
            <div>
              <p className="font-medium text-gray-800">Ver Archivos</p>
              <p className="text-sm text-gray-500">Gestionar archivos cargados</p>
            </div>
          </a>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
