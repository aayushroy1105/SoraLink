import React from "react"
import { RequestCategory } from "../types"

interface IconProps {
  className?: string
  size?: number
}

export const WaterIcon: React.FC<IconProps> = ({
  className = "w-7 h-7 text-[#202124]",
  size = 28,
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <path
      d="M8.5 7H23.5L21.5 25C21.5 26.1046 20.6046 27 19.5 27H12.5C11.3954 27 10.5 26.1046 10.5 25L8.5 7Z"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M10 14C11.5 13.5 13.5 14.5 16 14.5C18.5 14.5 20.5 13.5 22 14"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path
      d="M16 4C16 4 14.5 5.5 14.5 6.5C14.5 7.32843 15.1716 8 16 8C16.8284 8 17.5 7.32843 17.5 6.5C17.5 5.5 16 4 16 4Z"
      fill="#C8102E"
    />
  </svg>
)

export const BlanketIcon: React.FC<IconProps> = ({
  className = "w-7 h-7 text-[#202124]",
  size = 28,
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <path
      d="M6 10C6 8.34315 7.34315 7 9 7H23C24.6569 7 26 8.34315 26 10V14C26 15.6569 24.6569 17 23 17H9C7.34315 17 6 15.6569 6 14V10Z"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M6 14V21C6 22.6569 7.34315 24 9 24H23C24.6569 24 26 22.6569 26 21V17"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M10 12H22M10 19H19"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeDasharray="2 3"
    />
    <rect x="23" y="19" width="3" height="4" rx="0.5" fill="#C8102E" />
  </svg>
)

export const PillowIcon: React.FC<IconProps> = ({
  className = "w-7 h-7 text-[#202124]",
  size = 28,
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <path
      d="M5 11C5 8.79086 6.79086 7 9 7H23C25.2091 7 27 8.79086 27 11V21C27 23.2091 25.2091 25 23 25H9C6.79086 25 5 23.2091 5 21V11Z"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M11 16C13.5 17.5 18.5 17.5 21 16"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path
      d="M5 7L9 11M27 7L23 11M5 25L9 21M27 25L23 21"
      stroke="currentColor"
      strokeWidth="1.25"
      strokeLinecap="round"
    />
    <circle cx="16" cy="11" r="1.5" fill="#C8102E" />
  </svg>
)

export const AccessibilityIcon: React.FC<IconProps> = ({
  className = "w-7 h-7 text-[#202124]",
  size = 28,
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <circle cx="16" cy="7.5" r="3" stroke="currentColor" strokeWidth="1.75" />
    <path
      d="M12 14.5C12 13.5 13 12.5 14.5 12.5H17.5C19 12.5 20 13.5 20 14.5V19.5H16"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M12 21H18.5L20 25.5"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M9 19.5C9 23.0899 11.9101 26 15.5 26C18.15 26 20.4 24.4 21.3 22"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
    />
    <circle cx="23.5" cy="14" r="1.5" fill="#C8102E" />
  </svg>
)

export const CategoryIcon: React.FC<{
  category: RequestCategory
  className?: string
  size?: number
}> = ({ category, className, size = 28 }) => {
  switch (category) {
    case "water_request":
      return <WaterIcon className={className} size={size} />
    case "blanket_request":
      return <BlanketIcon className={className} size={size} />
    case "pillow_request":
      return <PillowIcon className={className} size={size} />
    case "accessibility_assist":
      return <AccessibilityIcon className={className} size={size} />
  }
}
