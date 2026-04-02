import { Component, type ErrorInfo, type ReactNode } from 'react'

interface MarkdownErrorBoundaryProps {
  children: ReactNode
  fallback: ReactNode
  resetKey?: string
}

interface MarkdownErrorBoundaryState {
  hasError: boolean
}

export class MarkdownErrorBoundary extends Component<
  MarkdownErrorBoundaryProps,
  MarkdownErrorBoundaryState
> {
  state: MarkdownErrorBoundaryState = {
    hasError: false,
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    // Keep the failure local to the markdown node without breaking the whole chat view.
  }

  componentDidUpdate(previousProps: MarkdownErrorBoundaryProps) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({ hasError: false })
    }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback
    }

    return this.props.children
  }
}
