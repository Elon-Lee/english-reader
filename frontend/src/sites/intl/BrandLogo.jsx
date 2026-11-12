import React from 'react'
import SharedBrandLogo from '../../components/BrandLogo'
import { BRAND_NAME, BRAND_MARK, BRAND_SLOGAN } from './brand.mjs'

export default function BrandLogo(props) {
  return <SharedBrandLogo {...props} name={BRAND_NAME} mark={BRAND_MARK} subtitle={props.subtitle ?? BRAND_SLOGAN} />
}
