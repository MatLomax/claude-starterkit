//go:build !unix

package install

// umask is 0 where the OS has none.
func umask() uint32 { return 0 }
