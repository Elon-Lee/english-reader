import React, { useState } from 'react'

export default function BookCover({ book, large = false, catalog = false, children }) {
  const url = book.coverUrl || ''
  const [failedUrl, setFailedUrl] = useState(null)
  const video = ['video', 'youtube'].includes(book.resourceType)
  return <div className={`${catalog ? 'catalog-cover-placeholder' : 'book-cover'} ${large ? (catalog ? 'large' : 'book-cover-large') : ''} ${video ? 'is-video' : ''} ${url && failedUrl !== url ? 'has-image' : 'text-cover'}`} style={{ '--cover': book.accent || '#dce9d8' }}>
    {url && failedUrl !== url ? <img src={url} alt={`${book.title}封面`} loading="lazy" onError={() => setFailedUrl(url)} /> : <><span className="cover-monogram">{String(book.title || '书').slice(0, 2).toUpperCase()}</span><small className="cover-title">{book.title}</small></>}
    {children}
  </div>
}
