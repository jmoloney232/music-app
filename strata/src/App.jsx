import { Routes, Route } from 'react-router-dom'
import Nav from './components/layout/Nav'
import Footer from './components/layout/Footer'
import Home from './pages/Home'
import Results from './pages/Results'
import DJMode from './pages/DJMode'
import Explore from './pages/Explore'
import Collections from './pages/Collections'
import CollectionDetail from './pages/CollectionDetail'

export default function App() {
  return (
    <div className="flex flex-col min-h-screen">
      <Nav />
      <main className="flex-1 pt-20">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/results" element={<Results />} />
          <Route path="/dj" element={<DJMode />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/collections" element={<Collections />} />
          <Route path="/collections/:id" element={<CollectionDetail />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
