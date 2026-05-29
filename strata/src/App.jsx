import { Routes, Route } from 'react-router-dom'
import Nav from './components/layout/Nav'
import Footer from './components/layout/Footer'
import Home from './pages/Home'
import Results from './pages/Results'

export default function App() {
  return (
    <div className="flex flex-col min-h-screen">
      <Nav />
      <main className="flex-1 pt-20">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/results" element={<Results />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
