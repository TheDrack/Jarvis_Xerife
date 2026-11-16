package com.thedrack.jarvismobile

import org.junit.Assert.assertEquals
import org.junit.Test

class VpnPackageFilterTest {
    @Test
    fun parsesCommaSemicolonAndWhitespaceSeparatedPackages() {
        assertEquals(
            listOf("com.example.one", "com.example.two", "com.example.three"),
            VpnPackageFilter.parse(" com.example.one,com.example.two; com.example.three ")
        )
    }

    @Test
    fun removesDuplicatesAndEmptyTokens() {
        assertEquals(
            listOf("com.example.one", "com.example.two"),
            VpnPackageFilter.parse("com.example.one,, com.example.one; ;com.example.two")
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsMoreThanFiftySelectedPackages() {
        VpnPackageFilter.parse((1..51).joinToString(",") { "com.example.app$it" })
    }

    @Test
    fun emptyFilterMeansAllAppsExceptJarvis() {
        assertEquals(emptyList<String>(), VpnPackageFilter.parse(" , ; \n "))
    }
}
