//go:build unix

package install

import "syscall"

// umask returns the process umask. Reading it means setting it, so it is set straight back.
func umask() uint32 {
	m := syscall.Umask(0)
	syscall.Umask(m)
	return uint32(m)
}
