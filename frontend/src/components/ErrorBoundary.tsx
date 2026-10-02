import { Component, type ReactNode } from "react";

/** Shows a recoverable message instead of a blank page if a view crashes. */
export class ErrorBoundary extends Component<{ children: ReactNode; onReset: () => void }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error("view crashed", error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="app">
        <main className="main">
          <section className="panel crash" role="alert">
            <h2 className="mydata__title">This twin couldn't be shown</h2>
            <p>
              Something in this view failed: <code>{this.state.error.message}</code>. Your data is safe on the server.
            </p>
            <div className="crash__actions">
              <button
                className="btn btn--primary"
                onClick={() => {
                  this.setState({ error: null });
                  this.props.onReset();
                }}
              >
                Go to the demo twin
              </button>
              <button className="btn" onClick={() => window.location.reload()}>
                Reload page
              </button>
            </div>
          </section>
        </main>
      </div>
    );
  }
}
